"""Kiểm tra sâu ứng viên trước breakout: dòng tiền (OBV, up/down vol, taker), phái sinh (OI, funding, L/S),
chỉ báo (BB squeeze, RSI, trend 1D, RS vs BTC) + vị trí trong nền 30 nến 4H.
Chạy: python deep_check.py CRV RAYSOL ...   → bảng + YYYY-MM-DD/deep_check.json
"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import breakout_scan as bs

sys.stdout.reconfigure(encoding="utf-8")
OUTDIR = Path(__file__).resolve().parent / date.today().isoformat(); OUTDIR.mkdir(exist_ok=True)


def ema(xs, n):
    a, e = 2 / (n + 1), xs[0]
    for x in xs:
        e = x * a + e * (1 - a)
    return e


def rsi(c, n=14):
    g = [max(c[i] - c[i - 1], 0) for i in range(len(c) - n, len(c))]
    d = [max(c[i - 1] - c[i], 0) for i in range(len(c) - n, len(c))]
    return 100 - 100 / (1 + sum(g) / max(sum(d), 1e-12))


def slope_pct(ys):
    n = len(ys); mx = (n - 1) / 2; my = sum(ys) / n
    b = sum((i - mx) * (y - my) for i, y in enumerate(ys)) / sum((i - mx) ** 2 for i in range(n))
    return b * n / (abs(my) or 1) * 100          # % thay đổi theo đường hồi quy trên cả đoạn


def bbw(c, n=20):
    m = sum(c[-n:]) / n; sd = (sum((x - m) ** 2 for x in c[-n:]) / n) ** 0.5
    return 4 * sd / m


def check(coin, btc):
    S = coin + "USDT"
    k = bs.kl(S, "4h", 300)[:-1]; d = bs.kl(S, "1d", 120)
    c = [x[4] for x in k]; v = [x[5] for x in k]; tb = [x[6] for x in k]; cd = [x[4] for x in d]
    # dòng tiền 40 nến
    obv, ob = 0, []
    for i in range(len(k) - 40, len(k)):
        obv += v[i] if c[i] > c[i - 1] else -v[i] if c[i] < c[i - 1] else 0; ob.append(obv)
    obv_sl = slope_pct([o + abs(min(ob)) + sum(v[-40:]) for o in ob])     # dịch dương để tính % ổn định
    px_sl = slope_pct(c[-40:])
    up = sum(v[i] for i in range(-30, 0) if c[i] >= c[i - 1]); dn = sum(v[i] for i in range(-30, 0) if c[i] < c[i - 1])
    buy30 = sum(tb[-30:]) / sum(v[-30:]) * 100
    vol8 = sum(v[-8:]) / 8 / (sum(v[-40:]) / 40)
    # BB squeeze: độ rộng BB hiện tại so với 120 nến
    widths = [bbw(c[:i]) for i in range(len(c) - 120, len(c) + 1)]
    sq = sum(1 for w in widths if w < widths[-1]) / len(widths) * 100     # percentile (thấp = nén)
    # nền 30 nến
    h30 = max(x[2] for x in k[-30:]); l30 = min(x[3] for x in k[-30:])
    # phái sinh
    try:
        oi = bs.get(f"/futures/data/openInterestHist?symbol={S}&period=4h&limit=31")
        oi_chg = (float(oi[-1]["sumOpenInterestValue"]) / float(oi[0]["sumOpenInterestValue"]) - 1) * 100
    except Exception:
        oi_chg = None
    try:
        fund = float(bs.get(f"/fapi/v1/premiumIndex?symbol={S}")["lastFundingRate"]) * 100
    except Exception:
        fund = None
    try:
        ls = float(bs.get(f"/futures/data/globalLongShortAccountRatio?symbol={S}&period=4h&limit=1")[-1]["longShortRatio"])
    except Exception:
        ls = None
    e34d, e89d = ema(cd, 34), ema(cd, 89)
    trend = "UP" if e34d > e89d and cd[-1] > e89d else "DN" if e34d < e89d and cd[-1] < e89d else "MIX"
    rs7 = ((cd[-1] / cd[-8]) / (btc[-1] / btc[-8]) - 1) * 100; rs30 = ((cd[-1] / cd[-31]) / (btc[-1] / btc[-31]) - 1) * 100
    r = dict(coin=coin, p=c[-1], base_top=h30, base_low=l30, dist=(h30 / c[-1] - 1) * 100, pos=(c[-1] - l30) / (h30 - l30),
             e200=(c[-1] / ema(c, 200) - 1) * 100, trend1d=trend, rsi4=rsi(c), rsid=rsi(cd),
             obv_sl=obv_sl, px_sl=px_sl, ud=up / max(dn, 1e-9), buy30=buy30, vol8=vol8, squeeze=sq,
             oi_chg=oi_chg, fund=fund, ls=ls, rs7=rs7, rs30=rs30, vol24=sum(x[5] for x in k[-6:]) / 1e6)
    # chấm điểm (mỗi yếu tố +1 / -1)
    pts, why = 0, []
    def add(cond, good, bad=None):
        nonlocal pts
        if cond is True: pts += 1; why.append("+" + good)
        elif cond is False and bad: pts -= 1; why.append("-" + bad)
    add(trend == "UP", "1D tăng", "1D không tăng")
    add(r["e200"] > 0, "trên EMA200 4H", "dưới EMA200 4H")
    add(True if (obv_sl > 0 and obv_sl > px_sl + 2) else (False if obv_sl < -2 else None), "OBV đi lên mạnh hơn giá (gom hàng)", f"OBV đi xuống ({obv_sl:+.1f}%)")
    add(r["ud"] > 1.15 if r["ud"] > 1.15 else (False if r["ud"] < 0.87 else None), f"vol nến tăng > giảm ({r['ud']:.2f})", f"vol nến giảm áp đảo ({r['ud']:.2f})")
    add(True if buy30 >= 51 else (False if buy30 <= 48.5 else None), f"taker mua {buy30:.0f}%", f"taker bán áp đảo ({buy30:.0f}% mua)")
    add(True if sq <= 25 else (False if sq >= 75 else None), f"BB nén (pct {sq:.0f})", f"BB đang giãn rộng (pct {sq:.0f})")
    if oi_chg is not None:
        add(True if oi_chg >= 8 and abs(px_sl) < 10 else (False if oi_chg <= -10 else None), f"OI +{oi_chg:.0f}% khi giá đi ngang", f"OI giảm {oi_chg:.0f}%")
    if fund is not None:
        add(True if fund <= 0.005 else (False if fund >= 0.03 else None), f"funding mát ({fund:.4f}%)", f"funding nóng ({fund:.4f}%)")
    add(True if r["dist"] <= 3 else (False if r["dist"] > 8 else None), f"sát đỉnh nền ({r['dist']:.1f}%)", f"còn xa đỉnh nền ({r['dist']:.1f}%)")
    add(True if rs30 > 0 else (False if rs30 < -10 else None), f"mạnh hơn BTC 30d ({rs30:+.0f}%)", f"yếu hơn BTC 30d ({rs30:+.0f}%)")
    add(False if r["rsi4"] > 72 else None, "", f"RSI 4H nóng ({r['rsi4']:.0f})")
    r["pts"], r["why"] = pts, why
    return r


if __name__ == "__main__":
    coins = [x.upper() for x in sys.argv[1:]]
    btc = [x[4] for x in bs.kl("BTCUSDT", "1d", 40)]
    with ThreadPoolExecutor(6) as ex:
        R = [r for r in ex.map(lambda c: (lambda: check(c, btc))() if True else None, coins) if r]
    R.sort(key=lambda r: -r["pts"])
    json.dump(R, open(OUTDIR / "deep_check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    for r in R:
        oi = f"{r['oi_chg']:+.0f}%" if r["oi_chg"] is not None else "n/a"
        fd = f"{r['fund']:.4f}%" if r["fund"] is not None else "n/a"
        print(f"\n[{r['pts']:+d}] {r['coin']:7} p={r['p']:<9.5g} nền {r['base_low']:.5g}–{r['base_top']:.5g} (cách đỉnh {r['dist']:.1f}%) | 1D {r['trend1d']} | "
              f"EMA200 4H {r['e200']:+.1f}% | RSI 4H/1D {r['rsi4']:.0f}/{r['rsid']:.0f} | OBV {r['obv_sl']:+.1f}% vs giá {r['px_sl']:+.1f}% | "
              f"up/down {r['ud']:.2f} | taker {r['buy30']:.0f}% | vol8 {r['vol8']:.2f} | BBpct {r['squeeze']:.0f} | OI {oi} | fund {fd} | "
              f"L/S {r['ls']} | RS BTC 7d/30d {r['rs7']:+.0f}/{r['rs30']:+.0f}%")
        print("        " + " ; ".join(r["why"]))
