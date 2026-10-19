"""Quét BREAKOUT có volume tốt trên khung 1H và 4H (long + short).

Breakout xác nhận khi:
  - 1 trong 2 nến ĐÃ ĐÓNG gần nhất đóng ngoài vùng nền (nền = N nến trước đó, bỏ 3 nến cuối)
  - volume nến breakout >= VMIN x trung bình nền; taker-buy (long) >= 47% / taker-sell (short) >= 47% (chỉ loại nến bị phe ngược chiều áp đảo)
  - giá hiện tại chưa chạy quá 1.2 ATR khỏi mép nền (còn retest được)
  - 1H phải cùng chiều trend 4H (EMA34 vs EMA89); 4H phải cùng chiều trend 1D
Entry = retest mép nền, STL = mép nền -/+ 1 ATR (khung đó) và ngoài giữa nền, TP = 0.6x và 1x chiều cao nền.
Kết quả lưu YYYY-MM-DD/breakout_scan.json. Chạy: python breakout_scan.py [thêm coin...]
"""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUTDIR = Path(__file__).resolve().parent / date.today().isoformat(); OUTDIR.mkdir(exist_ok=True)
F = "https://fapi.binance.com"
STOCK = {'SAMSUNG','MU','META','MSTR','KORU','DRAM','NVDA','TSLA','COIN','HOOD','AAPL','AMZN','GOOGL','CRCL','INTC','PLTR','AMD','EWY',
         'TQQQ','QQQ','SPY','XAG','XAU','LITE','SNDK','ORCL','MSFT','AVGO','NFLX','BABA','TSM','SKHYNIX','SKHY','BZ','PUMPBTC','QCOM',
         'NBIS','CL','NATGAS','NG','HG','SNXX','SOXL','SOXS','TNA','TZA','UVXY','SQQQ','XPT','XPD','WDC','CBRS','MVLL','MRVL','BE','RKLB'}
WATCH = ("XVG PENGU ZK PIPPIN SENT LAYER ZAMA ASTER TRUMP GIGGLE HYPE BCH ZEC ARKM FARTCOIN ARB FET ADA EIGEN ENA TRX "
         "JUP WLD PUMP FIL DOT RENDER ICP LIT NEAR INJ ETC UNI AVAX AAVE ONDO TAO SAND").split()
CFG = {"1h": dict(base=48, vmin=1.8, look=6), "4h": dict(base=30, vmin=1.4, look=3)}


def get(p):
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(F + p, timeout=20))
        except Exception as e:
            err = e; time.sleep(1.2)
    raise err


def ema(xs, n):
    a, e = 2 / (n + 1), xs[0]
    for x in xs:
        e = x * a + e * (1 - a)
    return e


def kl(sym, itv, n):
    return [(int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]))
            for x in get(f"/fapi/v1/klines?symbol={sym}&interval={itv}&limit={n}")]


def trend(k):
    c = [x[4] for x in k]; e34, e89 = ema(c, 34), ema(c, 89)
    return "UP" if e34 > e89 and c[-1] > e89 else "DN" if e34 < e89 and c[-1] < e89 else "MIX"


def scan(sym):
    out = []
    try:
        k1 = kl(sym, "1h", 150); k4 = kl(sym, "4h", 150); kd = kl(sym, "1d", 100)
    except Exception:
        return out
    if len(k1) < 120 or len(k4) < 120 or len(kd) < 90:
        return out
    tr4, trd = trend(k4), trend(kd)
    for tf, k, higher in (("1h", k1, tr4), ("4h", k4, trd)):
        cfg = CFG[tf]; n = len(k)
        o = [x[1] for x in k]; h = [x[2] for x in k]; l = [x[3] for x in k]; c = [x[4] for x in k]; v = [x[5] for x in k]; tb = [x[6] for x in k]
        tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, n)]; atr = sum(tr[-14:]) / 14
        base = slice(n - 3 - cfg["base"], n - 3)
        top, bot = max(h[base]), min(l[base]); width = (top - bot) / bot
        vavg = sum(v[base]) / cfg["base"]; p = c[-1]
        if not 0.03 <= width <= 0.30:
            continue
        # SẮP BREAKOUT: giá sát mép (<=0.5 ATR), volume 3 nến gần nhất tăng >=1.3x nền, cùng chiều trend lớn
        v3 = sum(v[-4:-1]) / 3 / vavg if vavg else 0; b3 = sum(tb[-4:-1]) / max(sum(v[-4:-1]), 1e-9) * 100
        if 0 <= top - p <= 0.5 * atr and v3 >= 1.3 and b3 >= 52 and higher == "UP":
            out.append(dict(sym=sym[:-4], tf=tf, side="NEAR-LONG", p=p, edge=top, entry=top, stop=top - 1.2 * atr,
                            tp1=top + 0.6 * (top - bot), tp2=top + (top - bot), rr1=0.6 * (top - bot) / (1.2 * atr), rr2=(top - bot) / (1.2 * atr),
                            volx=round(v3, 1), buy=round(b3), width=round(width * 100, 1), ext=round((p - top) / atr, 2), higher=higher, d1=trd, bar="chờ"))
        if 0 <= p - bot <= 0.5 * atr and v3 >= 1.3 and b3 <= 48 and higher == "DN":
            out.append(dict(sym=sym[:-4], tf=tf, side="NEAR-SHORT", p=p, edge=bot, entry=bot, stop=bot + 1.2 * atr,
                            tp1=bot - 0.6 * (top - bot), tp2=bot - (top - bot), rr1=0.6 * (top - bot) / (1.2 * atr), rr2=(top - bot) / (1.2 * atr),
                            volx=round(v3, 1), buy=round(b3), width=round(width * 100, 1), ext=round((bot - p) / atr, 2), higher=higher, d1=trd, bar="chờ"))
        for i in range(n - 2, n - 2 - cfg["look"], -1):  # các nến đã đóng gần nhất (n-1 là nến đang chạy)
            volx = v[i] / vavg if vavg else 0
            buy = tb[i] / v[i] * 100 if v[i] else 50
            if c[i] > top and volx >= cfg["vmin"] and buy >= 47 and higher != "DN" and (p - top) <= 1.5 * atr and p > top - 0.5 * atr:
                entry = top; stop = min(top - 1.0 * atr, (top + bot) / 2)
                tp1, tp2 = top + 0.6 * (top - bot), top + (top - bot)
                out.append(dict(sym=sym[:-4], tf=tf, side="LONG", p=p, edge=top, entry=entry, stop=stop, tp1=tp1, tp2=tp2,
                                rr1=(tp1 - entry) / (entry - stop), rr2=(tp2 - entry) / (entry - stop), volx=round(volx, 1),
                                buy=round(buy), width=round(width * 100, 1), ext=round((p - top) / atr, 2), higher=higher, d1=trd,
                                bar=datetime.fromtimestamp(k[i][0], timezone.utc).strftime("%d %H:%M")))
                break
            sell = 100 - buy
            if c[i] < bot and volx >= cfg["vmin"] and sell >= 47 and higher != "UP" and (bot - p) <= 1.5 * atr and p > 0 and p < bot + 0.5 * atr:
                entry = bot; stop = max(bot + 1.0 * atr, (top + bot) / 2)
                tp1, tp2 = bot - 0.6 * (top - bot), bot - (top - bot)
                out.append(dict(sym=sym[:-4], tf=tf, side="SHORT", p=p, edge=bot, entry=entry, stop=stop, tp1=tp1, tp2=tp2,
                                rr1=(entry - tp1) / (stop - entry), rr2=(entry - tp2) / (stop - entry), volx=round(volx, 1),
                                buy=round(buy), width=round(width * 100, 1), ext=round((bot - p) / atr, 2), higher=higher, d1=trd,
                                bar=datetime.fromtimestamp(k[i][0], timezone.utc).strftime("%d %H:%M")))
                break
    return out


if __name__ == "__main__":
    print("now", datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC"))
    T = [t for t in get("/fapi/v1/ticker/24hr") if t['symbol'].endswith("USDT") and t['symbol'][:-4] not in STOCK
         and t['symbol'] not in ("USDCUSDT", "FDUSDUSDT", "BTCDOMUSDT") and float(t['quoteVolume']) >= 20e6]
    syms = {t['symbol'] for t in sorted(T, key=lambda t: -float(t['quoteVolume']))[:150]}
    allsyms = {t['symbol'] for t in get("/fapi/v1/ticker/price")}
    syms |= {c + "USDT" for c in WATCH + [x.upper() for x in sys.argv[1:]] if c + "USDT" in allsyms}
    vol = {t['symbol']: float(t['quoteVolume']) / 1e6 for t in T}
    with ThreadPoolExecutor(12) as ex:
        R = [x for r in ex.map(scan, sorted(syms)) for x in r]
    for r in R:
        r['vol24'] = round(vol.get(r['sym'] + "USDT", 0)); r['watch'] = r['sym'] in WATCH
    json.dump(R, open(OUTDIR / "breakout_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Quét {len(syms)} coin → {len(R)} breakout có volume")
    for tf in ("4h", "1h"):
        for side in ("LONG", "SHORT", "NEAR-LONG", "NEAR-SHORT"):
            rows = sorted([x for x in R if x['tf'] == tf and x['side'] == side], key=lambda x: (-x['volx']))
            print(f"\n=== {tf.upper()} {side} ({len(rows)}) ===")
            for r in rows:
                print(f"{'★' if r['watch'] else ' '} {r['sym']:9} nến {r['bar']} | p={r['p']:<10g} mép nền {r['edge']:<10.6g} (nền {r['width']}%) "
                      f"đã chạy {r['ext']:+.2f} ATR | vol {r['volx']}x buy {r['buy']}% | entry {r['entry']:.6g} STL {r['stop']:.6g} "
                      f"({abs(r['entry']-r['stop'])/r['entry']*100:.1f}%) TP {r['tp1']:.6g}/{r['tp2']:.6g} RR {r['rr1']:.1f}/{r['rr2']:.1f} "
                      f"| trend lớn {r['higher']} 1D {r['d1']} | vol24 {r['vol24']}M")
