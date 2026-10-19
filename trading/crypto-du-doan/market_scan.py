"""Quét thị trường futures USDT Binance: tổng quan + tìm setup 'dễ đánh' (trend rõ, đang pullback về EMA, chưa extended)."""
import json, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from pathlib import Path as _Path
OUTDIR = _Path(__file__).resolve().parent / _date.today().isoformat()  # kết quả lưu theo ngày
OUTDIR.mkdir(exist_ok=True)


sys.stdout.reconfigure(encoding="utf-8")
API = "https://fapi.binance.com/fapi/v1/"
get = lambda path: json.load(urllib.request.urlopen(API + path, timeout=20))
SKIP = {"USDCUSDT", "FDUSDUSDT", "BTCDOMUSDT", "USDPUSDT", "TUSDUSDT"}


def ema(xs, n):
    k, e, out = 2 / (n + 1), xs[0], []
    for x in xs:
        e = x * k + e * (1 - k)
        out.append(e)
    return out


def rsi(xs, n=14):
    g = l = 0
    for a, b in zip(xs[-n - 1:-1], xs[-n:]):
        d = b - a
        g += max(d, 0); l += max(-d, 0)
    return 100 if l == 0 else 100 - 100 / (1 + g / l)


def atr(h, l, c, n=14):
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    return sum(tr[-n:]) / n


def kl(sym, itv, lim):
    r = get(f"klines?symbol={sym}&interval={itv}&limit={lim}")
    return [float(x[2]) for x in r], [float(x[3]) for x in r], [float(x[4]) for x in r], [float(x[7]) for x in r]


def analyze(t):
    s = t["symbol"]
    try:
        h4, l4, c4, v4 = kl(s, "4h", 200)
        hd, ld, cd, _ = kl(s, "1d", 120)
    except Exception:
        return None
    if len(c4) < 120 or len(cd) < 90:
        return None
    p = c4[-1]
    e34_4, e89_4 = ema(c4, 34)[-1], ema(c4, 89)[-1]
    e34_d, e89_d = ema(cd, 34)[-1], ema(cd, 89)[-1]
    a4 = atr(h4, l4, c4)
    hi30, lo30 = max(h4[-30:]), min(l4[-30:])
    up_d = p > e34_d > e89_d
    dn_d = p < e34_d < e89_d
    up_4 = p > e89_4 and e34_4 > e89_4
    dn_4 = p < e89_4 and e34_4 < e89_4
    d34 = (p - e34_4) / a4                      # khoảng cách tới EMA34 4H, tính theo ATR
    r = rsi(c4)
    pos = (p - lo30) / (hi30 - lo30) * 100 if hi30 > lo30 else 50
    vol_ratio = sum(v4[-6:]) / (sum(v4[-36:-6]) / 5)  # volume 24h so với TB 5 ngày trước
    score_long = (2 if up_d else 0) + (2 if up_4 else 0) + (2 if -0.8 <= d34 <= 0.8 else 0) + (1 if 40 <= r <= 58 else 0) + (1 if pos < 60 else 0)
    score_short = (2 if dn_d else 0) + (2 if dn_4 else 0) + (2 if -0.8 <= d34 <= 0.8 else 0) + (1 if 42 <= r <= 60 else 0) + (1 if pos > 40 else 0)
    return dict(sym=s[:-4], price=p, chg24=float(t["priceChangePercent"]), qvol=float(t["quoteVolume"]) / 1e6,
                chg7d=(p / c4[-43] - 1) * 100, up_d=up_d, dn_d=dn_d, up_4=up_4, dn_4=dn_4, d34=round(d34, 2),
                rsi=round(r, 1), atr_pct=round(a4 / p * 100, 2), pos30=round(pos), vol_ratio=round(vol_ratio, 2),
                e34_4=e34_4, e89_4=e89_4, e34_d=e34_d, hi30=hi30, lo30=lo30, a4=a4,
                score_long=score_long, score_short=score_short)


tick = [t for t in get("ticker/24hr") if t["symbol"].endswith("USDT") and t["symbol"] not in SKIP]
tick = sorted(tick, key=lambda t: -float(t["quoteVolume"]))[:70]
fund = {x["symbol"][:-4]: float(x["lastFundingRate"]) * 100 for x in get("premiumIndex")}
with ThreadPoolExecutor(12) as ex:
    rows = [r for r in ex.map(analyze, tick) if r]
for r in rows:
    r["fund"] = round(fund.get(r["sym"], 0), 4)

n = len(rows)
med = sorted(r["chg24"] for r in rows)[n // 2]
print(f"== TỔNG QUAN ({n} coin top volume) ==")
print(f"Trên EMA34 1D: {sum(r['price'] > r['e34_d'] for r in rows)}/{n} | Trend tăng 1D (P>EMA34>EMA89): {sum(r['up_d'] for r in rows)} | Trend giảm 1D: {sum(r['dn_d'] for r in rows)}")
print(f"Trend tăng 4H: {sum(r['up_4'] for r in rows)} | Trend giảm 4H: {sum(r['dn_4'] for r in rows)} | Median %24h: {med:+.2f}% | Funding TB: {sum(r['fund'] for r in rows)/n:+.4f}%")
for s in ("BTC", "ETH", "SOL", "BNB", "XRP"):
    r = next((x for x in rows if x["sym"] == s), None)
    if r:
        print(f"{s:5} {r['price']:<10g} 24h {r['chg24']:+.2f}% 7d {r['chg7d']:+.1f}% | 1D {'UP' if r['up_d'] else 'DN' if r['dn_d'] else 'MIX'} 4H {'UP' if r['up_4'] else 'DN' if r['dn_4'] else 'MIX'} | RSI4H {r['rsi']} | d34 {r['d34']} ATR | fund {r['fund']}%")
print("\n-- Top tăng / giảm 24h --")
for r in sorted(rows, key=lambda r: -r["chg24"])[:6] + sorted(rows, key=lambda r: r["chg24"])[:6]:
    print(f"{r['sym']:10} {r['chg24']:+6.2f}%  7d {r['chg7d']:+6.1f}%  vol {r['qvol']:.0f}M")
cols = "sym price chg24 chg7d rsi d34 atr_pct pos30 vol_ratio fund qvol".split()
print("\n== ỨNG VIÊN LONG (score >= 7) ==")
for r in sorted(rows, key=lambda r: (-r["score_long"], abs(r["d34"]))):
    if r["score_long"] >= 7:
        print(r["score_long"], {k: (round(r[k], 6) if isinstance(r[k], float) else r[k]) for k in cols + ["e34_4", "e89_4", "lo30", "hi30", "a4"]})
print("\n== ỨNG VIÊN SHORT (score >= 7) ==")
for r in sorted(rows, key=lambda r: (-r["score_short"], abs(r["d34"]))):
    if r["score_short"] >= 7:
        print(r["score_short"], {k: (round(r[k], 6) if isinstance(r[k], float) else r[k]) for k in cols + ["e34_4", "e89_4", "lo30", "hi30", "a4"]})

json.dump(rows, open(OUTDIR / "scan_rows.json", "w", encoding="utf-8"), ensure_ascii=False)
