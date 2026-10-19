"""Vẽ dự đoán đường giá (projection) cho 1 coin — 2 chế độ:

  analyze : python projection.py analyze HYPE 4h [--bars 150]
            -> in JSON mốc kỹ thuật (giá hiện tại, ATR, swing high/low, fib, pivot gần nhất)
               để chọn neckline / vùng vào lệnh / STL / target.

  render  : python projection.py render spec.json
            -> vẽ ảnh PNG (spec.out) + ghi file <out>_tv.json chứa danh sách lệnh draw_shape
               (time = unix giây) để vẽ lại y hệt lên TradingView qua MCP.

Dữ liệu nến: Binance Futures (fallback Spot). Coin không có trên Binance: truyền
"bars_file" trong spec (JSON list [{time(giây), open, high, low, close}, ...]).
"""
import json, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
INTERVAL_SEC = {"15m": 900, "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400,
                "6h": 21600, "12h": 43200, "1d": 86400, "1w": 604800}
TV_RES = {"15m": "15", "30m": "30", "1h": "60", "2h": "120", "4h": "240",
          "6h": "360", "12h": "720", "1d": "D", "1w": "W"}

COL = dict(bg="#131722", fg="#d1d4dc", grid="#2a2e39", up="#26a69a", down="#ef5350",
           level="#f5a623", zone="#2962ff", stop="#ff1744", inval="#e040fb", tp="#00e676",
           path_down="#ef5350", path_up="#26a69a", entry="#ffffff")


# ---------------------------------------------------------------- data
def norm_symbol(coin):
    s = coin.upper().replace("BINANCE:", "").replace(".P", "").replace("/", "")
    return s if s.endswith("USDT") else s + "USDT"


def fetch(coin, interval, limit=150, bars_file=None):
    if bars_file:
        rows = json.loads(Path(bars_file).read_text(encoding="utf-8"))
        return [dict(t=int(r["time"]), o=float(r["open"]), h=float(r["high"]),
                     l=float(r["low"]), c=float(r["close"])) for r in rows][-limit:]
    sym = norm_symbol(coin)
    for base in ("https://fapi.binance.com/fapi/v1/klines", "https://api.binance.com/api/v3/klines"):
        try:
            raw = json.load(urllib.request.urlopen(f"{base}?symbol={sym}&interval={interval}&limit={limit}", timeout=15))
            if raw:
                return [dict(t=r[0] // 1000, o=float(r[1]), h=float(r[2]), l=float(r[3]), c=float(r[4])) for r in raw]
        except urllib.error.HTTPError:
            continue
    sys.exit(f"Không lấy được nến {sym} {interval} từ Binance — dùng bars_file (lấy từ TradingView data_get_ohlcv).")


def atr(b, n=14):
    tr = [max(x["h"] - x["l"], abs(x["h"] - p["c"]), abs(x["l"] - p["c"])) for p, x in zip(b, b[1:])]
    return sum(tr[-n:]) / min(n, len(tr))


def pivots(b, k=3):
    hi, lo = [], []
    for i in range(k, len(b) - k):
        if b[i]["h"] == max(x["h"] for x in b[i - k:i + k + 1]):
            hi.append(i)
        if b[i]["l"] == min(x["l"] for x in b[i - k:i + k + 1]):
            lo.append(i)
    return hi, lo


def fmt_t(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d/%m %H:%M")


# ---------------------------------------------------------------- analyze
def analyze(coin, interval, limit):
    b = fetch(coin, interval, limit)
    n = len(b)
    ih = max(range(n), key=lambda i: b[i]["h"])
    il = min(range(n), key=lambda i: b[i]["l"])
    hi, lo = swing_h, swing_l = b[ih]["h"], b[il]["l"]
    up_leg = il < ih  # đáy trước đỉnh -> sóng tăng, fib hồi xuống
    rng = hi - lo
    fib = {str(r): round(hi - r * rng if up_leg else lo + r * rng, 6)
           for r in (0.236, 0.382, 0.5, 0.618, 0.706, 0.786)}
    ph, pl = pivots(b)
    out = dict(
        symbol=norm_symbol(coin), interval=interval, tv_symbol=f"BINANCE:{norm_symbol(coin)}.P",
        tv_resolution=TV_RES.get(interval), last_close=b[-1]["c"], last_bar_time=b[-1]["t"],
        last_bar=fmt_t(b[-1]["t"]), bars=n, atr14=round(atr(b), 6),
        swing_high=dict(price=swing_h, bar_offset=ih - (n - 1), time=fmt_t(b[ih]["t"])),
        swing_low=dict(price=swing_l, bar_offset=il - (n - 1), time=fmt_t(b[il]["t"])),
        leg="up (đáy->đỉnh, fib đo mức hồi xuống)" if up_leg else "down (đỉnh->đáy, fib đo mức hồi lên)",
        fib=fib,
        recent_pivot_highs=[dict(price=b[i]["h"], bar_offset=i - (n - 1), time=fmt_t(b[i]["t"])) for i in ph[-6:]],
        recent_pivot_lows=[dict(price=b[i]["l"], bar_offset=i - (n - 1), time=fmt_t(b[i]["t"])) for i in pl[-6:]],
        range_last_30=dict(high=max(x["h"] for x in b[-30:]), low=min(x["l"] for x in b[-30:])),
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- render
def rr(tr):
    risk = abs(tr["entry"] - tr["stop"])
    return [round(abs(t - tr["entry"]) / risk, 2) if risk else None for t in tr.get("targets", [])]


def render(spec_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    spec_path = Path(spec_path)
    S = json.loads(spec_path.read_text(encoding="utf-8"))
    interval = S.get("interval", "4h")
    step = INTERVAL_SEC[interval]
    b = fetch(S["symbol"], interval, S.get("bars", 150), S.get("bars_file"))
    n, last = len(b), len(b) - 1
    t_last = b[-1]["t"]
    tx = lambda k: t_last + int(k) * step          # offset nến -> unix time
    path = S["path"]                                # [[offset, price], ...] offset 0 = nến hiện tại
    path = [[0, b[-1]["c"]]] + (path[1:] if path[0][0] == 0 else path)  # luôn bắt đầu từ giá hiện tại
    horizon = max(p[0] for p in path)
    if S.get("prev"):
        horizon = max(horizon, round((S["prev"]["t0"] - t_last) / step) + max(k for k, _ in S["prev"]["path"]))
    right = horizon + max(12, horizon // 3)
    tv = []                                         # lệnh draw_shape cho TradingView

    def tv_add(shape, p1, p2=None, text=None, **ov):
        d = dict(shape=shape, point=dict(time=p1[0], price=round(p1[1], 6)))
        if p2:
            d["point2"] = dict(time=p2[0], price=round(p2[1], 6))
        if text:
            d["text"] = text
        if ov:
            d["overrides"] = json.dumps(ov)
        tv.append(d)

    fig, ax = plt.subplots(figsize=(15, 8), facecolor=COL["bg"])
    ax.set_facecolor(COL["bg"])
    for i, x in enumerate(b):
        col = COL["up"] if x["c"] >= x["o"] else COL["down"]
        ax.vlines(i, x["l"], x["h"], color=col, lw=0.8)
        ax.add_patch(Rectangle((i - 0.35, min(x["o"], x["c"])), 0.7,
                               max(abs(x["c"] - x["o"]), (x["h"] - x["l"]) * 0.02 + 1e-12), color=col))

    x_left_level = max(0, last - 80)
    # Mốc ngang (neckline, hỗ trợ/kháng cự)
    for lv in S.get("levels", []):
        c = lv.get("color", COL["level"])
        ax.axhline(lv["price"], color=c, lw=1.3)
        ax.text(x_left_level, lv["price"], f' {lv["label"]} {lv["price"]:g}', color=c, fontsize=9, va="bottom")
        tv_add("horizontal_line", (t_last, lv["price"]), linecolor=c, linewidth=2)
        tv_add("text", (b[x_left_level]["t"], lv["price"]), text=f'{lv["label"]} {lv["price"]:g}')

    # Vùng giá (vùng vào lệnh / fib)
    for z in S.get("zones", []):
        x0, x1 = z.get("from", 0), z.get("to", right)
        c = z.get("color", COL["zone"])
        ax.add_patch(Rectangle((last + x0, z["bottom"]), x1 - x0, z["top"] - z["bottom"], color=c, alpha=0.22))
        ax.text(last + x0 + 0.5, z["bottom"], f' {z["label"]} ({z["bottom"]:g}–{z["top"]:g})',
                color="#8fa8ff", fontsize=9, va="top")
        tv_add("rectangle", (tx(x0), z["top"]), (tx(x1), z["bottom"]),
               color=c, backgroundColor="rgba(41,98,255,0.18)", fillBackground=True)
        tv_add("text", (tx(x0), z["bottom"]), text=f'{z["label"]} {z["bottom"]:g}-{z["top"]:g}')

    # Đường dự đoán lần trước (so sánh): prev = {"t0": unix giây của nến gốc, "path": [...], "label": "..."}
    prev = S.get("prev")
    if prev:
        sh = round((prev["t0"] - t_last) / step)            # nến gốc cũ nằm ở offset âm so với hiện tại
        pp = [[k + sh, p] for k, p in prev["path"]]
        ax.plot([last + k for k, _ in pp], [p for _, p in pp], color="#9598a1", lw=1.6, ls=":", alpha=0.9)
        ax.text(last + pp[-1][0], pp[-1][1], f' {prev.get("label", "Dự đoán trước")}', color="#9598a1", fontsize=9, va="bottom")
        for (k0, p0), (k1, p1) in zip(pp, pp[1:]):
            tv_add("trend_line", (tx(k0), p0), (tx(k1), p1), linecolor="#9598a1", linewidth=1, linestyle=1)
        tv_add("text", (tx(pp[-1][0]), pp[-1][1]), text=prev.get("label", "Dự đoán trước"))

    # Đường dự đoán: màu theo chiều từng đoạn
    for (k0, p0), (k1, p1) in zip(path, path[1:]):
        c = COL["path_up"] if p1 >= p0 else COL["path_down"]
        ax.plot([last + k0, last + k1], [p0, p1], color=c, lw=2.2, ls="--")
        tv_add("trend_line", (tx(k0), p0), (tx(k1), p1), linecolor=c, linewidth=2, linestyle=2)

    # Lệnh: entry, STL, targets
    box = []
    for tr in S.get("trades", []):
        side = tr["side"].lower()
        k = tr.get("entry_bar", 0)
        seg0, seg1 = last + k - 3, last + min(right, k + tr.get("span", 14))
        mk = "v" if side == "short" else "^"
        ax.scatter([last + k], [tr["entry"]], marker=mk, s=140, color=COL["path_down" if side == "short" else "path_up"],
                   edgecolor="white", zorder=6)
        ax.hlines(tr["entry"], seg0, seg1, color=COL["entry"], lw=1, ls="-", alpha=0.7)
        ax.text(seg1, tr["entry"], f' {tr.get("label", side.upper())} {tr["entry"]:g}', color=COL["entry"], fontsize=9, va="center")
        ax.hlines(tr["stop"], seg0, seg1, color=COL["stop"], lw=1.6, ls="-")
        ax.text(seg1, tr["stop"], f' STL {tr["stop"]:g}', color=COL["stop"], fontsize=9, va="center", weight="bold")
        tv_add("trend_line", (tx(k - 3), tr["entry"]), (tx(k + tr.get("span", 14)), tr["entry"]), linecolor="#ffffff", linewidth=1)
        tv_add("text", (tx(k + tr.get("span", 14)), tr["entry"]), text=f'{tr.get("label", side.upper())} {tr["entry"]:g}')
        tv_add("trend_line", (tx(k - 3), tr["stop"]), (tx(k + tr.get("span", 14)), tr["stop"]), linecolor=COL["stop"], linewidth=2)
        tv_add("text", (tx(k + tr.get("span", 14)), tr["stop"]), text=f'STL {side} {tr["stop"]:g}')
        for j, t in enumerate(tr.get("targets", []), 1):
            ax.hlines(t, seg0, seg1, color=COL["tp"], lw=1.2, ls=":")
            ax.text(seg1, t, f" TP{j} {t:g}", color=COL["tp"], fontsize=9, va="center")
            tv_add("trend_line", (tx(k - 3), t), (tx(k + tr.get("span", 14)), t), linecolor=COL["tp"], linewidth=1, linestyle=1)
            tv_add("text", (tx(k + tr.get("span", 14)), t), text=f"TP{j} {side} {t:g}")
        rrs = rr(tr)
        box.append(f'{side.upper():5} entry {tr["entry"]:g} | STL {tr["stop"]:g} | TP '
                   + ", ".join(f"{t:g} (R:R {r})" for t, r in zip(tr.get("targets", []), rrs)))

    # Invalidation của cả kịch bản
    inv = S.get("invalidation")
    if inv:
        ax.axhline(inv["price"], color=COL["inval"], lw=1.4, ls="-.")
        ax.text(last + right * 0.35, inv["price"], f' INVALIDATION {inv["price"]:g} — {inv.get("note", "")}',
                color=COL["inval"], fontsize=9, va="bottom", weight="bold")
        tv_add("horizontal_line", (t_last, inv["price"]), linecolor=COL["inval"], linewidth=2, linestyle=1)
        tv_add("text", (tx(2), inv["price"]), text=f'INVALIDATION {inv["price"]:g} {inv.get("note", "")}')
        box.append(f'INVALIDATION {inv["price"]:g}: {inv.get("note", "")}')

    # Ghi chú kịch bản
    for note in S.get("notes", []):
        k, p = note["at"]
        ax.annotate(note["text"], (last + k, p), (last + k + note.get("dx", -25), p + note.get("dy", 0)),
                    color=COL["fg"], fontsize=9, arrowprops=dict(arrowstyle="->", color="#777"))
    if box:
        ax.text(0.01, 0.97, "\n".join(box), transform=ax.transAxes, va="top", ha="left", family="monospace",
                fontsize=9, color=COL["fg"], bbox=dict(boxstyle="round", fc="#1e222d", ec=COL["grid"]))

    # Trục
    all_p = [x["l"] for x in b] + [x["h"] for x in b] + [p for _, p in path] + [p for _, p in (prev or {}).get("path", [])]
    all_p += [tr["stop"] for tr in S.get("trades", [])] + [t for tr in S.get("trades", []) for t in tr.get("targets", [])]
    if inv:
        all_p.append(inv["price"])
    pad = (max(all_p) - min(all_p)) * 0.05
    ax.set_ylim(min(all_p) - pad, max(all_p) + pad)
    ax.set_xlim(0, last + right)
    ticks = list(range(0, last + right, max(1, (last + right) // 10)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([datetime.fromtimestamp(b[0]["t"] + i * step, timezone.utc).strftime("%d/%m") for i in ticks])
    ax.axvline(last, color="#555", lw=0.8, ls=":")
    ax.yaxis.tick_right()
    ax.tick_params(colors=COL["fg"])
    ax.grid(color=COL["grid"], lw=0.6)
    for s in ax.spines.values():
        s.set_color(COL["grid"])
    title = S.get("title") or f'{norm_symbol(S["symbol"])}.P · {interval.upper()} · Binance'
    ax.set_title(f'{title} — giá hiện tại {b[-1]["c"]:g} ({fmt_t(t_last)} UTC)  |  Kịch bản dự đoán, không phải lời khuyên đầu tư',
                 color=COL["fg"], loc="left", fontsize=11)
    plt.tight_layout()
    out = Path(S.get("out") or spec_path.with_suffix(".png"))
    plt.savefig(out, dpi=110, facecolor=COL["bg"])
    tv_path = out.with_name(out.stem + "_tv.json")
    tv_path.write_text(json.dumps(dict(tv_symbol=f'BINANCE:{norm_symbol(S["symbol"])}.P',
                                       tv_resolution=TV_RES.get(interval), drawings=tv),
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    # Biểu thức JS vẽ tất cả trong 1 lần gọi ui_evaluate; id hình lưu vào localStorage 've_du_doan_ids'
    js_items = []
    for d in tv:
        ov = json.loads(d["overrides"]) if "overrides" in d else {}
        if d["shape"] == "text":
            txt = d["text"]
            tc = (COL["stop"] if txt.startswith("STL") else COL["tp"] if txt.startswith("TP")
                  else COL["inval"] if txt.startswith("INVALIDATION") else COL["fg"])
            ov = {"color": tc, "fontsize": 11, "bold": tc != COL["fg"], **ov}
        js_items.append(dict(s=d["shape"], p=d["point"], p2=d.get("point2"), t=d.get("text"), o=ov))
    sym = f'BINANCE:{norm_symbol(S["symbol"])}.P'
    js = ("(() => { const c = window.TradingViewApi.activeChart(); const K = 've_du_doan_ids:' + c.symbol();"
          " if (!c.symbol().includes('" + norm_symbol(S["symbol"]) + "')) return 'SAI SYMBOL: chart đang là ' + c.symbol();"
          " const old = JSON.parse(localStorage.getItem(K) || '[]'); const live = new Set(c.getAllShapes().map(s => String(s.id)));"
          " let removed = 0; old.forEach(id => { if (live.has(id)) { c.removeEntity(id); removed++; } });"
          " const D = " + json.dumps(js_items, ensure_ascii=False)
          + "; let fails = 0; const ps = D.map(d => { const o = {shape: d.s, overrides: d.o, lock: false}; if (d.t) o.text = d.t;"
          " const mk = (p, p2) => p2 ? c.createMultipointShape([p, p2], o) : c.createShape(p, o);"
          " try { return mk(d.p, d.p2); } catch (e) { const t = Math.max(d.p.time, " + str(t_last) + "); fails++;"
          " try { return mk({time: t, price: d.p.price}, d.p2); } catch (e2) { return null; } } });"
          " Promise.all(ps.filter(Boolean)).then(ids => { const s = ids.map(String); window.__vdd_last = s;"
          " try { localStorage.setItem(K, JSON.stringify(s)); } catch (e) {} });"
          " return {symbol: c.symbol(), removed_old: removed, drawn: ps.filter(Boolean).length, of: D.length, moved_to_now: fails}; })()")
    js_path = out.with_name(out.stem + "_tv.js")
    js_path.write_text(js, encoding="utf-8")
    print(json.dumps(dict(png=str(out.resolve()), tv_json=str(tv_path.resolve()), tv_js=str(js_path.resolve()), drawings=len(tv),
                          last_close=b[-1]["c"], trades=box), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "analyze":
        lim = int(sys.argv[sys.argv.index("--bars") + 1]) if "--bars" in sys.argv else 150
        analyze(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else "4h", lim)
    elif len(sys.argv) == 3 and sys.argv[1] == "render":
        render(sys.argv[2])
    else:
        sys.exit(__doc__)
