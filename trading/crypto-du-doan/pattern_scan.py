"""Tìm coin có "form trước khi tăng" giống các đợt pump mẫu (INJ, PEPE, XMR) — khung 4H.

Cách làm:
  - Mẫu = 40 nến 4H ngay TRƯỚC nến pump (nến pump: volume >= 2.5x TB 30 nến, tăng >= 4%, đóng trên đỉnh 30 nến).
  - Đặc trưng: độ rộng nền 30 nến, vị trí giá trong nền, volume cạn (8 nến / 40 nến), ATR co lại,
    khoảng cách tới đỉnh nền, đáy nâng (độ dốc đáy), vị trí so với EMA200 4H, và HÌNH DẠNG đường giá (tương quan).
  - Coin hiện tại (nến đã đóng gần nhất) được chấm điểm giống từng mẫu → lấy mẫu giống nhất.
  - Bỏ coin đã pump rồi (giá đã vượt đỉnh nền > 3% hoặc có nến vol >= 2.5x trong 6 nến gần nhất).
Chạy: python pattern_scan.py [thêm coin...]   → in bảng + lưu YYYY-MM-DD/pattern_scan.json
"""
import json, math, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import breakout_scan as bs

sys.stdout.reconfigure(encoding="utf-8")
OUTDIR = Path(__file__).resolve().parent / date.today().isoformat(); OUTDIR.mkdir(exist_ok=True)
TEMPLATES = [("INJUSDT", "18/09 08:00"), ("INJUSDT", "16/10 00:00"), ("1000PEPEUSDT", "19/09 16:00"),
             ("1000PEPEUSDT", "20/10 12:00"), ("XMRUSDT", "30/08 12:00"), ("XMRUSDT", "18/09 12:00")]
W = 40


def ema(xs, n):
    a, e, out = 2 / (n + 1), xs[0], []
    for x in xs:
        e = x * a + e * (1 - a); out.append(e)
    return out


def feats(k, t):
    """Đặc trưng của 40 nến k[t-W:t] (t = chỉ số nến pump / nến ngay sau nến đóng cuối)."""
    win = k[t - W:t]
    if len(win) < W or t < 210:
        return None
    h = [x[2] for x in win]; l = [x[3] for x in win]; c = [x[4] for x in win]; v = [x[5] for x in win]
    h30, l30 = max(h[-30:]), min(l[-30:])
    tr = [max(k[i][2] - k[i][3], abs(k[i][2] - k[i - 1][4]), abs(k[i][3] - k[i - 1][4])) for i in range(t - W - 30, t)]
    atr_end, atr_start = sum(tr[-14:]) / 14, sum(tr[-44:-30]) / 14
    lows8 = [min(l[i:i + 8]) for i in range(0, W, 8)]                       # 5 đáy theo cụm 8 nến
    xs = range(len(lows8)); mx = sum(xs) / len(lows8); my = sum(lows8) / len(lows8)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, lows8)) / sum((x - mx) ** 2 for x in xs) / my * 100
    e200 = ema([x[4] for x in k[:t]], 200)[-1]
    mu = sum(c) / W; sd = (sum((x - mu) ** 2 for x in c) / W) ** 0.5 or 1
    return dict(width=(h30 - l30) / l30 * 100, pos=(c[-1] - l30) / (h30 - l30 or 1), dry=(sum(v[-8:]) / 8) / (sum(v) / W),
                atrc=atr_end / (atr_start or atr_end), dist=(h30 / c[-1] - 1) * 100, slope=slope, e200=(c[-1] / e200 - 1) * 100,
                shape=[(x - mu) / sd for x in c], h30=h30, l30=l30, close=c[-1])


SCALE = dict(width=8, pos=0.25, dry=0.35, atrc=0.3, dist=4, slope=1.0, e200=6)


def score(f, g):
    corr = sum(a * b for a, b in zip(f["shape"], g["shape"])) / W
    dist = math.sqrt(sum(((f[x] - g[x]) / s) ** 2 for x, s in SCALE.items()) / len(SCALE))
    return round(50 * (corr + 1) / 2 + 50 * math.exp(-dist), 1), round(corr, 2)


def build_templates():
    T = []
    for sym, when in TEMPLATES:
        k = bs.kl(sym, "4h", 500)
        idx = next((i for i, x in enumerate(k) if datetime.fromtimestamp(x[0], timezone.utc).strftime("%d/%m %H:%M") == when), None)
        f = feats(k, idx) if idx else None
        if f:
            f["name"] = f"{sym.replace('USDT', '')} {when[:5]}"; T.append(f)
    return T


def scan(sym, T):
    try:
        k = bs.kl(sym, "4h", 500)[:-1]                                      # bỏ nến đang chạy
    except Exception:
        return None
    t = len(k); f = feats(k, t)
    if not f:
        return None
    va = sum(x[5] for x in k[-36:-6]) / 30
    if f["close"] > f["h30"] * 1.03 or any(x[5] >= 2.5 * va for x in k[-6:]):   # đã pump rồi
        return None
    best = max(((score(f, g), g["name"]) for g in T), key=lambda z: z[0][0])
    return dict(sym=sym.replace("USDT", ""), score=best[0][0], corr=best[0][1], like=best[1], p=f["close"],
                base_top=f["h30"], base_low=f["l30"], width=round(f["width"], 1), pos=round(f["pos"], 2),
                dry=round(f["dry"], 2), atrc=round(f["atrc"], 2), dist=round(f["dist"], 1), slope=round(f["slope"], 2), e200=round(f["e200"], 1))


if __name__ == "__main__":
    T = build_templates()
    print("Mẫu:", ", ".join(g["name"] for g in T))
    for g in T:
        print(f"  {g['name']:16} nền {g['width']:.1f}% | vị trí {g['pos']:.2f} | vol cạn {g['dry']:.2f} | ATR co {g['atrc']:.2f} | "
              f"cách đỉnh nền {g['dist']:.1f}% | đáy nâng {g['slope']:+.2f}%/cụm | so EMA200 4H {g['e200']:+.1f}%")
    tick = [t for t in bs.get("/fapi/v1/ticker/24hr") if t["symbol"].endswith("USDT") and t["symbol"][:-4] not in bs.STOCK
            and float(t["quoteVolume"]) >= 15e6]
    syms = {t["symbol"] for t in sorted(tick, key=lambda t: -float(t["quoteVolume"]))[:180]}
    syms |= {c + "USDT" for c in bs.WATCH + [x.upper() for x in sys.argv[1:]]}
    syms -= {"INJUSDT", "1000PEPEUSDT", "XMRUSDT", "BTCUSDT", "USDCUSDT", "BTCDOMUSDT"}
    with ThreadPoolExecutor(10) as ex:
        R = [r for r in ex.map(lambda s: scan(s, T), sorted(syms)) if r]
    R.sort(key=lambda r: -r["score"])
    json.dump(R, open(OUTDIR / "pattern_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nQuét {len(syms)} coin → {len(R)} coin chưa pump. Top 15 giống form trước khi tăng:")
    print("coin       điểm  hình  giống         giá        đỉnh nền    đáy nền   nền%  vị trí volcạn ATRco cáchđỉnh đáynâng EMA200")
    for r in R[:15]:
        print(f"{r['sym']:10} {r['score']:5} {r['corr']:5}  {r['like']:13} {r['p']:<10.5g} {r['base_top']:<11.5g} {r['base_low']:<9.5g} "
              f"{r['width']:5} {r['pos']:6} {r['dry']:6} {r['atrc']:5} {r['dist']:7}% {r['slope']:+6} {r['e200']:+6}%")
