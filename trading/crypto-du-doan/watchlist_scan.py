"""Phân tích các coin trong watchlist TradingView: trend 4H/1D, vị trí giá, VOLUME chi tiết -> coin nào mua được.

Volume: (1) vol 24h, (2) vol 6 nến 4H gần nhất so với TB 30 nến trước, (3) % taker-buy (lệnh mua chủ động) 24h,
(4) tổng volume nến tăng / nến giảm 20 nến 4H, (5) độ dốc OBV 20 nến.
Dữ liệu: Binance Futures, coin không có trên Binance thì lấy MEXC Futures. Kết quả lưu YYYY-MM-DD/watchlist_scan.json.
Chạy:  python watchlist_scan.py BTC ETH PENGU ...   (không truyền -> dùng danh sách mặc định trong file)
"""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUTDIR = Path(__file__).resolve().parent / date.today().isoformat()
OUTDIR.mkdir(exist_ok=True)
DEFAULT = ("XVG PENGU ZK PIPPIN SENT LAYER ZAMA ASTER TRUMP GIGGLE HYPE BCH XMR ZEC ARKM FARTCOIN ARB FET ADA EIGEN ENA TRX "
           "JUP WLD PUMP MNT FIL DOT RENDER ICP LIT NEAR INJ ETC UNI AVAX AAVE ONDO TAO SAND").split()


def get(url):
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20))
        except Exception as e:
            err = e; time.sleep(1.2)
    raise err


def bars(coin, itv, n):
    """Trả list nến [t, o, h, l, c, quoteVol, takerBuyQuoteVol or None] + nguồn."""
    try:
        k = get(f"https://fapi.binance.com/fapi/v1/klines?symbol={coin}USDT&interval={itv}&limit={n}")
        if k:
            return [(x[0] // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10])) for x in k], "Binance"
    except Exception:
        pass
    m = {"4h": "Hour4", "1d": "Day1", "1h": "Min60"}[itv]
    d = get(f"https://contract.mexc.com/api/v1/contract/kline/{coin}_USDT?interval={m}")["data"]
    rows = [(d["time"][i], d["open"][i], d["high"][i], d["low"][i], d["close"][i], d["amount"][i], None) for i in range(len(d["time"]))]
    return rows[-n:], "MEXC"


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


def analyze(coin):
    try:
        k4, src = bars(coin, "4h", 200)
        kd, _ = bars(coin, "1d", 120)
    except Exception as e:
        return dict(sym=coin, err=str(e)[:80])
    if len(k4) < 120 or len(kd) < 60:
        return dict(sym=coin, err="thiếu dữ liệu")
    o = [x[1] for x in k4]; h = [x[2] for x in k4]; l = [x[3] for x in k4]; c = [x[4] for x in k4]; v = [x[5] for x in k4]
    cd = [x[4] for x in kd]
    p = c[-1]
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]; atr = sum(tr[-14:]) / 14
    e34, e89, e200 = ema(c, 34), ema(c, 89), ema(c, 200); d34, d89 = ema(cd, 34), ema(cd, 89)
    K = 3; n = len(h)
    ph = [h[i] for i in range(n - 60, n - K) if h[i] == max(h[i - K:i + K + 1])]
    pl = [l[i] for i in range(n - 60, n - K) if l[i] == min(l[i - K:i + K + 1])]
    hl = len(pl) >= 2 and pl[-1] > pl[-2]; lh = len(ph) >= 2 and ph[-1] < ph[-2]
    hi30, lo30 = max(h[-30:]), min(l[-30:])
    # ---- VOLUME
    vol24 = sum(v[-6:])
    volx = vol24 / (sum(v[-36:-6]) / 5)                     # vol 24h so với TB/ngày của 5 ngày trước
    tb = [x[6] for x in k4[-6:]]
    buy_pct = (sum(tb) / vol24 * 100) if all(t is not None for t in tb) and vol24 else None
    upv = sum(v[i] for i in range(n - 20, n) if c[i] >= o[i]); dnv = sum(v[i] for i in range(n - 20, n) if c[i] < o[i])
    ud = upv / dnv if dnv else 9.9
    obv = [0.0]
    for i in range(1, n):
        obv.append(obv[-1] + (v[i] if c[i] > c[i - 1] else -v[i] if c[i] < c[i - 1] else 0))
    obv_slope = (obv[-1] - obv[-21]) / (sum(v[-20:]) or 1)   # -1..+1: dòng tiền ròng 20 nến
    # ---- PHÂN LOẠI
    trend_d = "UP" if d34 > d89 and cd[-1] > d89 else "DN" if d34 < d89 and cd[-1] < d89 else "MIX"
    trend_4 = "UP" if e34 > e89 and p > e89 else "DN" if e34 < e89 and p < e89 else "MIX"
    pos = (p - lo30) / (hi30 - lo30) * 100 if hi30 > lo30 else 50
    d34a = (p - e34) / atr
    vol_ok = (ud >= 1.1) + (obv_slope > 0.05) + (buy_pct is None or buy_pct >= 50) + (volx >= 0.9)
    score = (2 if trend_d == "UP" else -2 if trend_d == "DN" else 0) + (2 if trend_4 == "UP" else -2 if trend_4 == "DN" else 0) \
        + (1 if hl else 0) - (1 if lh else 0) + (1 if -1.0 <= d34a <= 1.0 else -1 if d34a > 2.2 else 0) + (vol_ok - 2) \
        - (1 if rsi(c) > 72 else 0)
    # entry/STL gợi ý cho long
    entry = min(p, max(e34, (pl[-1] if pl else lo30) + 0.1 * atr))
    stop = min(min(pl[-1] if pl else lo30, e89) - 0.3 * atr, entry - 1.0 * atr)
    tp1 = next((x for x in reversed(ph) if x > entry * 1.005), hi30); tp2 = max(hi30, tp1 + 1.0 * atr)
    rr = (tp1 - entry) / (entry - stop) if entry > stop else 0
    return dict(sym=coin, src=src, p=p, trend_d=trend_d, trend_4=trend_4, hl=hl, lh=lh, pos=round(pos), d34a=round(d34a, 2),
                rsi4=round(rsi(c)), rsid=round(rsi(cd)), atr=round(atr / p * 100, 2), vol24=round(vol24 / 1e6, 1), volx=round(volx, 2),
                buy_pct=round(buy_pct, 1) if buy_pct is not None else None, ud=round(ud, 2), obv=round(obv_slope, 2), vol_ok=vol_ok,
                score=score, entry=entry, stop=stop, tp1=tp1, tp2=tp2, rr=round(rr, 2), e34=e34, e89=e89, hi30=hi30, lo30=lo30)


def btc():
    k4, _ = bars("BTC", "4h", 200); kd, _ = bars("BTC", "1d", 120)
    c = [x[4] for x in k4]; cd = [x[4] for x in kd]
    return dict(p=c[-1], e34=ema(c, 34), e89=ema(c, 89), rsi4=round(rsi(c)), d34=ema(cd, 34), d89=ema(cd, 89), rsid=round(rsi(cd)),
                chg24=round((c[-1] / c[-7] - 1) * 100, 2), chg7=round((c[-1] / c[-43] - 1) * 100, 2),
                hi30=max(x[2] for x in k4[-30:]), lo30=min(x[3] for x in k4[-30:]))


if __name__ == "__main__":
    coins = [x.upper() for x in sys.argv[1:]] or DEFAULT
    print("now", datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC"))
    b = btc()
    print(f"BTC {b['p']:,.0f} | 24h {b['chg24']:+}% 7d {b['chg7']:+}% | 4H EMA34 {b['e34']:,.0f} EMA89 {b['e89']:,.0f} RSI {b['rsi4']} | "
          f"1D EMA34 {b['d34']:,.0f} EMA89 {b['d89']:,.0f} RSI {b['rsid']} | range30 4H {b['lo30']:,.0f}–{b['hi30']:,.0f}")
    with ThreadPoolExecutor(10) as ex:
        R = list(ex.map(analyze, coins))
    json.dump(dict(btc=b, rows=R), open(OUTDIR / "watchlist_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sorted([r for r in R if "err" not in r], key=lambda r: -r["score"])
    print(f"\n{'coin':9}{'nguồn':8}{'giá':>11} {'1D':>4} {'4H':>4} HL LH {'pos':>4} {'d34':>6} {'rsi4':>5} {'vol24M':>7} {'volx':>5} {'buy%':>5} {'up/dn':>6} {'obv':>6} vOK score | entry → STL → TP1 (RR)")
    for r in ok:
        print(f"{r['sym']:9}{r['src']:8}{r['p']:>11.6g} {r['trend_d']:>4} {r['trend_4']:>4} {'✓' if r['hl'] else '·':>2} {'✓' if r['lh'] else '·':>2} "
              f"{r['pos']:>4} {r['d34a']:>+6.2f} {r['rsi4']:>5} {r['vol24']:>7} {r['volx']:>5} {str(r['buy_pct'] or '-'):>5} {r['ud']:>6} {r['obv']:>+6.2f} "
              f"{r['vol_ok']:>3}/4 {r['score']:>4} | {r['entry']:.6g} → {r['stop']:.6g} → {r['tp1']:.6g} ({r['rr']})")
    for r in R:
        if "err" in r:
            print("LỖI", r["sym"], r["err"])
