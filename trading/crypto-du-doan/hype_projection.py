"""Vẽ chart HYPE 4H + đường giá dự đoán (kịch bản H&S -> hồi về vùng fib 0.706-0.786 -> long về 98)."""
import json, urllib.request
from datetime import datetime, timezone
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

H4 = 4 * 3600 * 1000
url = "https://fapi.binance.com/fapi/v1/klines?symbol=HYPEUSDT&interval=4h&limit=150"
raw = json.load(urllib.request.urlopen(url))
t = [r[0] for r in raw]
o, h, l, c = ([float(r[i]) for r in raw] for i in (1, 2, 3, 4))
n = len(t)

# Swing dùng cho fib: đáy 14/09 -> đỉnh (head)
swing_low, swing_high = min(l[-120:]), max(h)
fib = lambda r: swing_high - r * (swing_high - swing_low)
f706, f786 = fib(0.706), fib(0.786)
neckline = 89.66

# Đường dự đoán: (số nến tính từ nến hiện tại, giá)
path = [(0, c[-1]), (3, 88.6), (9, 83.6), (11, 85.4), (16, (f706 + f786) / 2 + 0.3),
        (24, neckline), (27, 88.3), (36, swing_high)]
low_idx = 4  # điểm đáy của kịch bản

BG, FG, GRID = "#131722", "#d1d4dc", "#2a2e39"
fig, ax = plt.subplots(figsize=(15, 7.5), facecolor=BG)
ax.set_facecolor(BG)
for i in range(n):
    col = "#26a69a" if c[i] >= o[i] else "#ef5350"
    ax.vlines(i, l[i], h[i], color=col, lw=0.8)
    ax.add_patch(Rectangle((i - 0.35, min(o[i], c[i])), 0.7, max(abs(c[i] - o[i]), 0.02), color=col))

last = n - 1
# Neckline + vùng long
ax.axhline(neckline, color="#f5a623", lw=1.3)
ax.text(last - 70, neckline + 0.4, f"Neckline {neckline}", color="#f5a623", fontsize=9)
ax.add_patch(Rectangle((last, f786), 40, f706 - f786, color="#2962ff", alpha=0.25))
ax.text(last + 1, f786 - 1.1, f"0.706–0.786  ({f786:.1f}–{f706:.1f})  vùng long", color="#8fa8ff", fontsize=9)
ax.axhline(swing_high, xmin=0, xmax=1, color="#888", lw=0.8, ls=":")
ax.text(last + 30, swing_high + 0.4, f"TP {swing_high:.2f}", color="#26a69a", fontsize=10, weight="bold")

# Đường dự đoán
xs = [last + k for k, _ in path]
ys = [p for _, p in path]
ax.plot(xs[: low_idx + 1], ys[: low_idx + 1], color="#ef5350", lw=2, ls="--")
ax.plot(xs[low_idx:], ys[low_idx:], color="#26a69a", lw=2, ls="--")
ax.scatter([xs[low_idx]], [ys[low_idx]], s=180, facecolor="none", edgecolor="white", lw=1.5, zorder=5)
ax.annotate("Short: retest neckline thất bại", (xs[1], ys[1]), (xs[1] - 40, ys[1] - 6),
            color=FG, fontsize=9, arrowprops=dict(arrowstyle="->", color="#777"))

# Trục thời gian
ticks = list(range(0, last + 40, 18))
ax.set_xticks(ticks)
ax.set_xticklabels([datetime.fromtimestamp((t[0] + i * H4) / 1000, timezone.utc).strftime("%d/%m") for i in ticks])
ax.set_xlim(0, last + 42)
ax.set_ylim(min(l) - 1, swing_high + 3)
ax.yaxis.tick_right()
ax.tick_params(colors=FG)
ax.grid(color=GRID, lw=0.6)
for s in ax.spines.values():
    s.set_color(GRID)
ax.set_title(f"HYPEUSDT.P · 4H · Binance — giá hiện tại {c[-1]:.2f}  |  Kịch bản dự đoán (không phải lời khuyên đầu tư)",
             color=FG, loc="left", fontsize=11)
plt.tight_layout()
plt.savefig("hype_projection.png", dpi=110, facecolor=BG)
print("low", swing_low, "high", swing_high, "f706", round(f706, 2), "f786", round(f786, 2), "last", c[-1])
