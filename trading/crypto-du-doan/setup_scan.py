"""Quét kèo long/short có xác nhận 1H (không bắt dao rơi) + đọc sentiment BTC 1H."""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from datetime import date as _date
from pathlib import Path as _Path
OUTDIR = _Path(__file__).resolve().parent / _date.today().isoformat()  # kết quả lưu theo ngày
OUTDIR.mkdir(exist_ok=True)


sys.stdout.reconfigure(encoding="utf-8")
F = "https://fapi.binance.com"
STOCK = {'SAMSUNG','MU','META','MSTR','KORU','DRAM','NVDA','TSLA','COIN','HOOD','AAPL','AMZN','GOOGL','CRCL','INTC','PLTR','AMD','EWY',
         'TQQQ','QQQ','SPY','XAG','XAU','LITE','SNDK','ORCL','MSFT','AVGO','NFLX','BABA','TSM','SKHYNIX','SKHY','BZ','PUMPBTC','QCOM',
         'NBIS','CL','NATGAS','NG','HG'}
SKIP = {'USDCUSDT', 'FDUSDUSDT', 'BTCDOMUSDT'}


def get(p):
    for i in range(3):
        try:
            return json.load(urllib.request.urlopen(F + p, timeout=20))
        except Exception as e:
            err = e; time.sleep(1.5)
    raise err


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
    return [float(x[2]) for x in k], [float(x[3]) for x in k], [float(x[4]) for x in k], [float(x[7]) for x in k]


def btc_sentiment():
    h, l, c, v = kl("BTCUSDT", "1h", 240)
    p = c[-1]; e34, e89, e200 = ema(c, 34), ema(c, 89), ema(c, 200)
    ph, pl = pivots(h, l, 3, 72)
    hh = len(ph) >= 2 and ph[-1][1] > ph[-2][1]; hl = len(pl) >= 2 and pl[-1][1] > pl[-2][1]
    lh = len(ph) >= 2 and ph[-1][1] < ph[-2][1]; ll = len(pl) >= 2 and pl[-1][1] < pl[-2][1]
    tk = get("/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=1h&limit=6")
    taker = [round(float(x['buySellRatio']), 2) for x in tk]
    score = (1 if p > e34 else -1) + (1 if e34 > e89 else -1) + (1 if p > e200 else -1) + (1 if hl else -1 if ll else 0) + (1 if hh else -1 if lh else 0)
    mood = "TĂNG" if score >= 3 else "GIẢM" if score <= -3 else "TRUNG TÍNH / ĐI NGANG"
    return dict(p=p, e34=e34, e89=e89, e200=e200, rsi=round(rsi(c)), ph=[round(x[1]) for x in ph[-3:]], pl=[round(x[1]) for x in pl[-3:]],
                hh=hh, hl=hl, lh=lh, ll=ll, taker=taker, score=score, mood=mood, chg6=round((p / c[-7] - 1) * 100, 2),
                chg24=round((p / c[-25] - 1) * 100, 2))


def analyze(t):
    s = t['symbol']
    try:
        h4, l4, c4, _ = kl(s, "4h", 150)
        h1, l1, c1, v1 = kl(s, "1h", 200)
    except Exception:
        return None
    if len(c4) < 120 or len(c1) < 150:
        return None
    p = c1[-1]
    a4 = atr(h4, l4, c4); a1 = atr(h1, l1, c1)
    e34_4, e89_4 = ema(c4, 34), ema(c4, 89)
    e34_1, e89_1 = ema(c1, 34), ema(c1, 89)
    ph1, pl1 = pivots(h1, l1, 3, 72)
    if len(ph1) < 2 or len(pl1) < 2:
        return None
    hi30, lo30 = max(h4[-30:]), min(l4[-30:])
    r1 = rsi(c1); r4 = rsi(c4)
    out = []
    # ---- LONG: 4H tăng + 1H đã tạo đáy cao hơn và lấy lại EMA34 1H (không bắt dao rơi)
    up4 = c4[-1] > e89_4 and e34_4 > e89_4
    hl1 = pl1[-1][1] > pl1[-2][1]
    if up4 and hl1 and p >= e34_1 * 0.998 and r1 < 68 and r4 < 70:
        sup = pl1[-1][1]
        entry = max(sup, min(e34_1, p))                         # mua ở EMA34 1H hoặc đáy 1H gần nhất
        stop = sup - 0.35 * a4
        tgt1 = max(x[1] for x in ph1[-3:]) if max(x[1] for x in ph1[-3:]) > entry * 1.004 else hi30
        tgt2 = hi30 if hi30 > tgt1 * 1.003 else hi30 + a4
        rr1 = (tgt1 - entry) / (entry - stop) if entry > stop else 0
        rr2 = (tgt2 - entry) / (entry - stop) if entry > stop else 0
        if rr1 >= 1.5 and abs(entry / p - 1) <= 0.02:
            out.append(dict(side="LONG", entry=entry, stop=stop, tp1=tgt1, tp2=tgt2, rr1=rr1, rr2=rr2))
    # ---- SHORT: 4H giảm hoặc đỉnh range + 1H đã tạo đỉnh thấp hơn và nằm dưới EMA34 1H
    dn4 = c4[-1] < e89_4 and e34_4 < e89_4
    top_rng = (p - lo30) / (hi30 - lo30) > 0.75 if hi30 > lo30 else False
    lh1 = ph1[-1][1] < ph1[-2][1]
    if (dn4 or top_rng) and lh1 and p <= e34_1 * 1.002 and r1 > 32 and r4 > 30:
        res = ph1[-1][1]
        entry = min(res, max(e34_1, p))
        stop = res + 0.35 * a4
        tgt1 = min(x[1] for x in pl1[-3:]) if min(x[1] for x in pl1[-3:]) < entry * 0.996 else lo30
        tgt2 = lo30 if lo30 < tgt1 * 0.997 else lo30 - a4
        rr1 = (entry - tgt1) / (stop - entry) if stop > entry else 0
        rr2 = (entry - tgt2) / (stop - entry) if stop > entry else 0
        if rr1 >= 1.5 and abs(entry / p - 1) <= 0.02:
            out.append(dict(side="SHORT", entry=entry, stop=stop, tp1=tgt1, tp2=tgt2, rr1=rr1, rr2=rr2, ctx="trend 4H giảm" if dn4 else "đỉnh range"))
    if not out:
        return None
    vr = sum(v1[-6:]) / (sum(v1[-54:-6]) / 8)
    return [dict(o, sym=s[:-4], p=p, r1=round(r1), r4=round(r4), atr4=round(a4 / p * 100, 2), risk=round(abs(o['entry'] - o['stop']) / o['entry'] * 100, 2),
                 vol=round(float(t['quoteVolume']) / 1e6), volx=round(vr, 2), chg24=float(t['priceChangePercent'])) for o in out]


if __name__ == "__main__":
    print("now", datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC"))
    b = btc_sentiment()
    print(f"BTC 1H: {b['p']:,.0f} | 6h {b['chg6']:+}% 24h {b['chg24']:+}% | EMA34 {b['e34']:,.0f} EMA89 {b['e89']:,.0f} EMA200 {b['e200']:,.0f} | RSI {b['rsi']}"
          f" | đỉnh {b['ph']} đáy {b['pl']} | HH {b['hh']} HL {b['hl']} LH {b['lh']} LL {b['ll']} | taker {b['taker']} | score {b['score']} → {b['mood']}")
    T = [t for t in get("/fapi/v1/ticker/24hr") if t['symbol'].endswith("USDT") and t['symbol'] not in SKIP and t['symbol'][:-4] not in STOCK]
    T = sorted(T, key=lambda t: -float(t['quoteVolume']))[:130]
    T = [t for t in T if float(t['quoteVolume']) >= 30e6]
    fund = {x['symbol'][:-4]: float(x['lastFundingRate']) * 100 for x in get("/fapi/v1/premiumIndex")}
    with ThreadPoolExecutor(12) as ex:
        res = [x for r in ex.map(analyze, T) if r for x in r]
    for r in res:
        r['fund'] = round(fund.get(r['sym'], 0), 4)
    json.dump(dict(btc=b, setups=res), open(OUTDIR / "setup_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for side in ("LONG", "SHORT"):
        print(f"\n=== {side} ===")
        for r in sorted([x for x in res if x['side'] == side], key=lambda x: -x['rr1']):
            print(f"{r['sym']:9} p={r['p']:<10g} entry {r['entry']:<10.6g} ({(r['entry']/r['p']-1)*100:+.2f}%) STL {r['stop']:<10.6g} (risk {r['risk']}%) "
                  f"TP {r['tp1']:.6g}/{r['tp2']:.6g} RR {r['rr1']:.1f}/{r['rr2']:.1f} | RSI1H {r['r1']} RSI4H {r['r4']} ATR4H {r['atr4']}% volx {r['volx']} "
                  f"fund {r['fund']:+.4f} vol {r['vol']}M 24h {r['chg24']:+.1f}% {r.get('ctx','')}")
