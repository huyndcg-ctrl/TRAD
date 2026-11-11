"""QA: kiểm tra tự động bộ công cụ quét (chạy lại bất cứ lúc nào: python qa_check.py).

 1. Chỉ báo trong core khớp công thức tham chiếu (EMA, RSI, ATR).
 2. Không nhìn trước: tín hiệu scan_all thấy tại nến i (chỉ có dữ liệu tới i) trùng với tín hiệu backtest ghi nhận tại i.
 3. Backtest không dùng dữ liệu tương lai: cắt bớt nến phía sau không làm đổi tín hiệu phía trước.
 4. simulate(): các ca tính tay (SL, TP1 rồi SL, TP2, nến chạm cả SL và TP).
 5. Bộ lọc chất lượng: coin lớn phải qua, token cổ phiếu / coin trong danh sách không chơi phải bị loại.
 6. alerts.build(): đủ 3 alert/kèo, đúng chiều cross, tag khớp cleanup_alerts, ✅ short dùng Pine 2 nến, ✅ long on_bar_close.
 7. journal: ca tổng hợp (vào, TP2, huỷ, không đuổi, thay kèo mới).
"""
import json, random, re, sys

import core, backtest as bt, scan_all, alerts, journal

OK = FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond: OK += 1
    else: FAIL += 1
    print(("  ✔ " if cond else "  ✘ LỖI ") + name + (f" — {extra}" if extra else ""))


print("1. Chỉ báo")
xs = [float(i % 7 + i * 0.1) for i in range(300)]
a = 2 / 35; e = xs[0]
for x in xs: e = x * a + e * (1 - a)
check("EMA34 khớp công thức", abs(core.ema(xs, 34) - e) < 1e-9)
g = sum(max(xs[i] - xs[i - 1], 0) for i in range(286, 300)); d = sum(max(xs[i - 1] - xs[i], 0) for i in range(286, 300))
check("RSI14 khớp công thức", abs(core.rsi(xs) - (100 - 100 / (1 + g / d))) < 1e-9)
k = core.kl("BTCUSDT", "4h", 300)
tr = [max(k[i][2] - k[i][3], abs(k[i][2] - k[i - 1][4]), abs(k[i][3] - k[i - 1][4])) for i in range(len(k) - 14, len(k))]
check("ATR14 khớp công thức", abs(core.atr_k(k) - sum(tr) / 14) < 1e-6)
check("atr_series[-1] = atr_k", abs(core.atr_series(k)[-1] - core.atr_k(k)) < 1e-6)

print("2–3. Không nhìn trước (5 coin × 150 điểm cắt)")
random.seed(7); bad_live = bad_cut = n_sig = 0
for sym in ("BTCUSDT", "SOLUSDT", "LINKUSDT", "HYPEUSDT", "XRPUSDT"):
    K = core.kl(sym, "4h", 1500, cache=False)[:-1]; D = core.kl(sym, "1d", 400, cache=False)[:-1]
    full = bt.prep(K, D)
    for i in random.sample(range(200, full["n"] - 3), 150):
        ref = {x[0]: x for x in bt.candidates(full, i)}
        cut = bt.prep(K[:i + 1], [x for x in D if x[0] + 86400 <= K[i][0] + 14400])      # chỉ dữ liệu có tại lúc nến i đóng
        live = {x[0] for x in scan_all.bt_candidates_live(cut, i)}
        for name in ("BO_L", "PB_L", "PB_S", "BD_S", "BO_L_alert", "BD_S_alert"):
            n_sig += name in ref
            if (name in ref) != (name in live): bad_live += 1
        cut2 = bt.prep(K[:i + 3], D)
        if {x[0]: x[4] for x in bt.candidates(cut2, i) if x[0] in ("BO_L", "PB_L", "PB_S", "BD_S")} != {n: x[4] for n, x in ref.items() if n in ("BO_L", "PB_L", "PB_S", "BD_S")}:
            bad_cut += 1
check("scan_all (live) thấy đúng tín hiệu backtest tại cùng nến", bad_live == 0, f"{n_sig} tín hiệu đối chiếu, lệch {bad_live}")
check("cắt dữ liệu tương lai không đổi tín hiệu/STL quá khứ", bad_cut == 0, f"lệch {bad_cut}")

print("4. simulate()")
def S_of(bars):   # bars: [(h, l, c)]
    return dict(h=[b[0] for b in bars], l=[b[1] for b in bars], c=[b[2] for b in bars], n=len(bars))
fee = bt.FEE * 100 / 10
check("long chạm SL → −1R", abs(bt.simulate(S_of([(101, 89, 95)]), 0, "L", 100, 90)[0] - (-1 - fee)) < 1e-9)
check("long TP1 rồi SL → +0.25R", abs(bt.simulate(S_of([(116, 99, 110), (111, 89, 95)]), 0, "L", 100, 90)[0] - (0.25 - fee)) < 1e-9)
check("long TP1 + TP2 → +2R", abs(bt.simulate(S_of([(116, 99, 110), (126, 105, 120)]), 0, "L", 100, 90)[0] - (2 - fee)) < 1e-9)
check("nến chạm cả SL lẫn TP tính SL", abs(bt.simulate(S_of([(130, 89, 120)]), 0, "L", 100, 90)[0] - (-1 - fee)) < 1e-9)
check("short TP2 → +2R", abs(bt.simulate(S_of([(101, 84, 86), (90, 74, 76)]), 0, "S", 100, 110)[0] - (2 - fee)) < 1e-9)
check("entry sai phía STL bị từ chối", bt.simulate(S_of([(101, 89, 95)]), 0, "L", 100, 105) is None)

print("5. Bộ lọc chất lượng")
V = {t["symbol"]: float(t["quoteVolume"]) for t in core.get("/fapi/v1/ticker/24hr")}
q = lambda s: core.quality(s, core.kl(s, "4h", 300), core.kl(s, "1d", 150), V.get(s, 0))
for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "XRPUSDT"):
    r = q(s); check(f"{s} qua bộ lọc", r[0], "; ".join(r[1]))
for s in ("EWZUSDT", "NVDAUSDT", "XAUUSDT", "PAXGUSDT"):
    check(f"{s} bị coi là TradFi", core.is_tradfi(s))
for s in ("INITUSDT", "NILUSDT"):
    try:
        r = q(s); check(f"{s} bị loại", not r[0], "; ".join(r[1]))
    except Exception as ex:
        check(f"{s} bị loại", True, f"không còn dữ liệu ({ex})")
U = {t["symbol"] for t in core.universe(150)}
check("universe không chứa token TradFi", not any(core.is_tradfi(s) for s in U), f"{len(U)} coin")

print("6. alerts.build()")
P = dict(date="2026-11-11", btc_cancel=dict(long_below=72690, short_above=74500), picks=[
    dict(coin="HYPE", side="short", level=70.35, confirm=2, stop=73.0, tp1=67.0, tp2=63.9, no_chase=69.0, cancel=73.0, size_r=0.3, why="lý do"),
    dict(coin="1000PEPE", side="long", level=0.00562, confirm=1, stop=0.00532, tp1=0.006, tp2=0.0064, cancel=0.0052, why="lý do")])
A, T, dm = alerts.build(P)
cond = lambda coin, kind: next(b["payload"] for c, px, kd, b in A if c == coin and kd == kind)
check("3 alert/kèo + 2 alert BTC", len(A) == 8, str(len(A)))
c = cond("HYPE", "✅")["conditions"][0]
check("✅ short = Pine 2 nến, on_bar_close 4H", c["type"] == "pine_alert" and c["series"][0]["inputs"]["in_2"] == 2 and c["series"][0]["inputs"]["in_1"] == "short" and c["frequency"] == "on_bar_close" and c["resolution"] == "240")
check("⏳ short = cross_down 1 phút bắn 1 lần", cond("HYPE", "⏳")["conditions"][0]["type"] == "cross_down" and cond("HYPE", "⏳")["conditions"][0]["frequency"] == "on_first_fire")
check("❌ short = 4H đóng TRÊN mức huỷ", cond("HYPE", "❌")["conditions"][0]["type"] == "cross_up" and cond("HYPE", "❌")["conditions"][0]["frequency"] == "on_bar_close")
c = cond("1000PEPE", "✅")["conditions"][0]
check("✅ long = cross_up on_bar_close 4H, chart BINANCE", c["type"] == "cross_up" and c["frequency"] == "on_bar_close" and "BINANCE:1000PEPEUSDT.P" in cond("1000PEPE", "✅")["symbol"])
check("❌ long = 4H đóng DƯỚI mức huỷ", cond("1000PEPE", "❌")["conditions"][0]["type"] == "cross_down")
check("chỉ ✅ mới chứa chữ VÀO LONG/SHORT", all(("✅ VÀO" in b["payload"]["message"]) == (kd == "✅") for _, _, kd, b in A))
check("⏳ long ghi CHƯA BUY", "CHƯA BUY" in cond("1000PEPE", "⏳")["message"])
TAG = re.compile(r'\[(\S+) [\d.,]+ · (?:kịch bản|nhánh giảm) (\d\d)/(\d\d)\]\s*$')
check("mọi tag khớp regex của cleanup_alerts", all(TAG.search(b["payload"]["message"].strip()) for *_, b in A))
check("không có số dạng mũ (1e-05)", not any(re.search(r"\de-\d", b["payload"]["message"]) for *_, b in A))

print("7. journal (nến giả)")
def bars(closes, t0=1000000, rng=0.2):
    return [(t0 + i * 14400, c, c + rng, c - rng, c, 1.0, 0.5) for i, c in enumerate(closes)] + [(t0 + len(closes) * 14400, 0, 0, 0, 0, 0, 0)]
def run(closes, **kw):
    e = dict(coin="TEST", side="short", level=100, confirm=2, stop=104, tp1=96, tp2=92, no_chase=None, cancel=104, btc_cancel=None, created=1000000 + 2 * 14400 + 60)
    e.update(kw); real = core.kl
    core.kl = lambda *a, **k: bars(closes)
    try: return journal.score_one(e, [], kw.get("until"))
    finally: core.kl = real
r = run([101, 101, 101, 99.5, 99, 97, 95.5, 93, 91.5])
check("short: ✅ ở nến thứ 2 đóng dưới mốc, rồi TP2", r["status"] == "TP2" and r["entry"] == 99, f"{r['status']} vào {r['entry']} {r['r']}R")
r = run([101, 101, 101, 99.5, 101, 105])
check("1 nến dưới mốc rồi bật lại → không vào; đóng trên mức huỷ → huỷ", r["status"] == "huỷ" and r["entry"] is None, r["status"])
r = run([101, 101, 101, 99.5, 95], no_chase=97)
check("✅ khi giá đã qua mức không đuổi → không đuổi", r["status"] == "không đuổi", r["status"])
r = run([101, 101, 101, 101, 101, 99.5, 99], until=1000000 + 4 * 14400)
check("có kèo mới cùng coin trước khi ✅ → thay kèo mới", r["status"] == "thay kèo mới", r["status"])
r = run([101, 99.5, 99, 98.9, 98.8], created=1000000 + 3 * 14400 + 60)
check("2 nến đã đóng dưới mốc TRƯỚC khi tạo kèo → ✅ không bắn lại", r["entry"] is None, f"{r['status']} vào {r['entry']}")
r = run([101, 99.5, 99, 98.9, 98.8])
check("nến 1 đóng dưới mốc trước khi tạo kèo, nến 2 sau → ✅ ở nến 2 (giống Pine)", r["entry"] == 99, f"{r['status']} vào {r['entry']}")
r = run([101, 101, 101, 99.5, 99, 104.5])
check("vào rồi chạm STL → SL ≈ −1R", r["status"] == "SL" and -1.1 < r["r"] <= -1.0, f"{r['status']} {r['r']}")

print(f"\nKẾT QUẢ QA: {OK} đạt, {FAIL} lỗi")
sys.exit(1 if FAIL else 0)
