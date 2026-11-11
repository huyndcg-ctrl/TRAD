"""Quét kèo theo KHUNG 4H (ít nhiễu hơn 1H): sentiment BTC 4H+1D, kèo pullback theo trend 1D, kèo breakout 4H.

STL đặt ngoài đỉnh/đáy 4H và cách entry tối thiểu 1 x ATR 4H. Kết quả lưu vào thư mục ngày (YYYY-MM-DD/setup_scan_4h.json).
Chạy:  python setup_scan_4h.py
Ghi chú: scan_all.py là bản quét đầy đủ (định nghĩa trùng backtest, có kỳ vọng R). File này giữ lại cho routine cũ.
PULLBACK SHORT (short khi hồi) chỉ có kỳ vọng dương khi BTC 4H giảm — xem expectancy.json. BREAKOUT: vào ngay, không chờ retest.
"""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUTDIR = Path(__file__).resolve().parent / date.today().isoformat()
OUTDIR.mkdir(exist_ok=True)
import core
from core import get, STOCK          # lõi chung
SKIP = {'USDCUSDT', 'FDUSDUSDT', 'BTCDOMUSDT'}
MIN_VOL = 30e6       # volume 24h tối thiểu (USDT)
MAX_ATR4 = 0.05      # ATR 4H tối đa 5% giá — bỏ coin bơm/xả mạnh


def tier(vol_m):
    """Hạng ưu tiên theo volume 24h (triệu USDT): A ≥100M, B 30–100M, C <30M."""
    return "A" if vol_m >= 100 else "B" if vol_m >= 30 else "C"
MAX_ENTRY_DIST = 0.04  # entry cách giá hiện tại tối đa 4%
MIN_RR1 = 1.5




def ema(xs, n):
    a, e = 2 / (n + 1), xs[0]
    for x in xs:
        e = x * a + e * (1 - a)
    return e


def rsi(xs, n=14):
    g = l = 0
    for a, b in zip(xs[-n - 1:-1], xs[-n:]):
        d = b - a; g += max(d, 0); l += max(-d, 0)
    return 100 if l == 0 else 100 - 100 / (1 + g / l)


def atr(h, l, c, n=14):
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    return sum(tr[-n:]) / n


def pivots(h, l, k=3, look=60):
    n = len(h)
    ph = [(i, h[i]) for i in range(n - look, n - k) if h[i] == max(h[i - k:i + k + 1])]
    pl = [(i, l[i]) for i in range(n - look, n - k) if l[i] == min(l[i - k:i + k + 1])]
    return ph, pl


def kl(sym, itv, n):
    k = get(f"/fapi/v1/klines?symbol={sym}&interval={itv}&limit={n}")
    return ([float(x[2]) for x in k], [float(x[3]) for x in k], [float(x[4]) for x in k], [float(x[7]) for x in k])


def btc_mood():
    h, l, c, _ = kl("BTCUSDT", "4h", 200)
    hd, ld, cd, _ = kl("BTCUSDT", "1d", 150)
    p = c[-1]; e34, e89, e200 = ema(c, 34), ema(c, 89), ema(c, 200); d34, d89 = ema(cd, 34), ema(cd, 89)
    ph, pl = pivots(h, l, 3, 60)
    hl = len(pl) >= 2 and pl[-1][1] > pl[-2][1]; ll = len(pl) >= 2 and pl[-1][1] < pl[-2][1]
    hh = len(ph) >= 2 and ph[-1][1] > ph[-2][1]; lh = len(ph) >= 2 and ph[-1][1] < ph[-2][1]
    s = (1 if p > e34 else -1) + (1 if e34 > e89 else -1) + (1 if p > e200 else -1) + (1 if hl else -1 if ll else 0) \
        + (1 if hh else -1 if lh else 0) + (1 if d34 > d89 else -1) + (1 if p > d34 else -1)
    mood = "TĂNG" if s >= 4 else "GIẢM" if s <= -4 else "ĐI NGANG / LƯỠNG LỰ"
    return dict(p=p, e34=e34, e89=e89, e200=e200, d34=d34, d89=d89, rsi4=round(rsi(c)), rsid=round(rsi(cd)),
                ph=[round(x[1]) for x in ph[-3:]], pl=[round(x[1]) for x in pl[-3:]], hh=hh, hl=hl, lh=lh, ll=ll,
                hi30=max(h[-30:]), lo30=min(l[-30:]), score=s, mood=mood, chg24=round((p / c[-7] - 1) * 100, 2))


def analyze(t):
    s = t['symbol']
    try:
        h, l, c, v = kl(s, "4h", 200)
        hd, ld, cd, _ = kl(s, "1d", 120)
    except Exception:
        return []
    if len(c) < 150 or len(cd) < 90:
        return []
    p = c[-1]; a = atr(h, l, c)
    if a > MAX_ATR4 * p:
        return []
    e34, e89 = ema(c, 34), ema(c, 89); d34, d89 = ema(cd, 34), ema(cd, 89)
    ph, pl = pivots(h, l, 3, 60)
    if len(ph) < 2 or len(pl) < 2:
        return []
    hi30, lo30 = max(h[-30:]), min(l[-30:])
    r4 = rsi(c); vr = sum(v[-6:]) / (sum(v[-36:-6]) / 5)
    base = dict(sym=s[:-4], p=p, r4=round(r4), rd=round(rsi(cd)), atr=round(a / p * 100, 2), volx=round(vr, 2),
                vol=round(float(t['quoteVolume']) / 1e6), chg24=float(t['priceChangePercent']))
    out = []
    up_d, dn_d = d34 > d89 and cd[-1] > d89, d34 < d89 and cd[-1] < d89
    # ---------- PULLBACK LONG: 1D tăng + 4H tăng + đáy 4H nâng dần, mua ở EMA34 4H / đáy 4H
    if up_d and e34 > e89 and p > e89 and pl[-1][1] > pl[-2][1] and r4 < 70:
        sup = pl[-1][1]
        entry = min(p, max(e34, sup + 0.1 * a))
        stop = min(sup, e89) - 0.3 * a
        stop = min(stop, entry - 1.0 * a)
        highs = [x[1] for x in ph if x[1] > entry * 1.005]
        tp1 = highs[-1] if highs else hi30
        tp2 = max(hi30, tp1) if max(hi30, tp1) > tp1 * 1.005 else tp1 + 1.5 * a
        rr1, rr2 = (tp1 - entry) / (entry - stop), (tp2 - entry) / (entry - stop)
        if rr1 >= MIN_RR1 and (p - entry) / p <= MAX_ENTRY_DIST:
            out.append(dict(base, type="PULLBACK", side="LONG", entry=entry, stop=stop, tp1=tp1, tp2=tp2, rr1=rr1, rr2=rr2,
                            why=f"1D tăng, 4H đáy nâng {pl[-2][1]:.6g}→{sup:.6g}, entry EMA34 4H"))
    # ---------- PULLBACK SHORT: 1D giảm + 4H giảm + đỉnh 4H hạ dần, bán ở EMA34 4H / đỉnh 4H
    if dn_d and e34 < e89 and p < e89 and ph[-1][1] < ph[-2][1] and r4 > 30:
        res = ph[-1][1]
        entry = max(p, min(e34, res - 0.1 * a))
        stop = max(res, e89) + 0.3 * a
        stop = max(stop, entry + 1.0 * a)
        lows = [x[1] for x in pl if x[1] < entry * 0.995]
        tp1 = lows[-1] if lows else lo30
        tp2 = min(lo30, tp1) if min(lo30, tp1) < tp1 * 0.995 else tp1 - 1.5 * a
        rr1, rr2 = (entry - tp1) / (stop - entry), (entry - tp2) / (stop - entry)
        if rr1 >= MIN_RR1 and (entry - p) / p <= MAX_ENTRY_DIST:
            out.append(dict(base, type="PULLBACK", side="SHORT", entry=entry, stop=stop, tp1=tp1, tp2=tp2, rr1=rr1, rr2=rr2,
                            why=f"1D giảm, 4H đỉnh hạ {ph[-2][1]:.6g}→{res:.6g}, entry EMA34 4H"))
    # ---------- BREAKOUT 4H: nến 4H đã đóng trên đỉnh nền 30 nến (trước 3 nến gần nhất), volume >= 1.5x, 1D tăng
    bh, bl = max(h[-33:-3]), min(l[-33:-3])
    width = (bh - bl) / bl
    if up_d and any(x > bh for x in c[-3:-1]) and p > bh and max(v[-3:]) / (sum(v[-33:-3]) / 30) >= 1.5 and 0.05 <= width <= 0.35:
        entry = p                                    # vào ngay sau nến 4H đóng xác nhận (backtest: tốt hơn chờ retest)
        stop = min(bh - 1.0 * a, e34 - 0.2 * a)
        tp1 = bh + (bh - bl) * 0.6; tp2 = bh + (bh - bl)
        rr1, rr2 = (tp1 - entry) / (entry - stop), (tp2 - entry) / (entry - stop)
        if rr1 >= MIN_RR1 and (p - entry) / p <= MAX_ENTRY_DIST:
            out.append(dict(base, type="BREAKOUT", side="LONG", entry=entry, stop=stop, tp1=tp1, tp2=tp2, rr1=rr1, rr2=rr2,
                            why=f"đóng 4H trên đỉnh nền {bh:.6g} (nền {width*100:.0f}%), vol {max(v[-3:])/(sum(v[-33:-3])/30):.1f}x, vào ngay"))
    return out


if __name__ == "__main__":
    print("now", datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC"))
    b = btc_mood()
    print(f"BTC 4H: {b['p']:,.0f} (24h {b['chg24']:+}%) | 4H EMA34 {b['e34']:,.0f} EMA89 {b['e89']:,.0f} EMA200 {b['e200']:,.0f} RSI {b['rsi4']}"
          f" | 1D EMA34 {b['d34']:,.0f} EMA89 {b['d89']:,.0f} RSI {b['rsid']} | đỉnh 4H {b['ph']} đáy 4H {b['pl']} | range30 {b['lo30']:,.0f}–{b['hi30']:,.0f}"
          f" | score {b['score']} → {b['mood']}")
    T = [t for t in get("/fapi/v1/ticker/24hr") if t['symbol'].endswith("USDT") and t['symbol'] not in SKIP
         and not core.is_tradfi(t['symbol']) and t['symbol'][:-4] not in core.BLACKLIST and float(t['quoteVolume']) >= MIN_VOL]
    T = sorted(T, key=lambda t: -float(t['quoteVolume']))[:130]
    fund = {x['symbol'][:-4]: float(x['lastFundingRate']) * 100 for x in get("/fapi/v1/premiumIndex")}
    with ThreadPoolExecutor(12) as ex:
        res = [x for r in ex.map(analyze, T) for x in r]
    for r in res:
        r['fund'] = round(fund.get(r['sym'], 0), 4)
        r['risk'] = round(abs(r['entry'] - r['stop']) / r['entry'] * 100, 2)
        r['tier'] = tier(r['vol'])
    json.dump(dict(btc=b, setups=res), open(OUTDIR / "setup_scan_4h.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for typ, side in (("PULLBACK", "LONG"), ("PULLBACK", "SHORT"), ("BREAKOUT", "LONG")):
        rows = sorted([x for x in res if x['type'] == typ and x['side'] == side], key=lambda x: (x['tier'], -x['rr1']))
        print(f"\n=== {typ} {side} ({len(rows)}) ===")
        for r in rows:
            print(f"[{r['tier']}] {r['sym']:9} p={r['p']:<10g} entry {r['entry']:<10.6g}({(r['entry']/r['p']-1)*100:+.2f}%) STL {r['stop']:<10.6g}(risk {r['risk']}%)"
                  f" TP {r['tp1']:.6g}/{r['tp2']:.6g} RR {r['rr1']:.1f}/{r['rr2']:.1f} | RSI4H {r['r4']} RSI1D {r['rd']} ATR {r['atr']}% volx {r['volx']}"
                  f" fund {r['fund']:+.4f} vol {r['vol']}M | {r['why']}")
