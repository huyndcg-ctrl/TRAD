"""QUÉT MỘT LỆNH: chế độ thị trường + BTC/ETH + mọi loại kèo 4H, định nghĩa TRÙNG với backtest.py nên dùng được kỳ vọng R.

Tín hiệu (nến 4H đã đóng gần nhất = i):
  BO_L   ✅ breakout long vừa xác nhận ở nến i (vol ≥1.5x)        → vào NGAY (không chờ retest)
  BD_S   1/2: nến i đóng dưới đáy nền (vol ≥1.5x) → CHỜ nến kế    | 2/2: nến i-1 phá + nến i vẫn đóng dưới → vào
  PB_L   long hồi về EMA34/Kijun 4H rồi đóng xanh (1D tăng + 4H tăng)
  PB_S   short hồi lên EMA34/Kijun rồi đóng đỏ (4H giảm)
  NEAR_L / NEAR_S  giá cách đỉnh/đáy 30 nến ≤ 1 ATR → đặt alert ⏳/✅ chờ nến 4H đóng qua mốc
Mỗi kèo có: entry tham chiếu, STL (theo backtest, ≥1 ATR), TP1 = 1.5R, TP2 = 2.5R, kỳ vọng R của setup trong chế độ hiện tại
(expectancy.json do backtest.py tạo), cờ "ổn định" = dương ở cả hai nửa giai đoạn backtest.
Coin phải qua bộ lọc chất lượng (core.quality). Coin bị loại được liệt kê riêng kèm lý do.

Chạy: python scan_all.py [COIN thêm ...]   → in bảng + lưu YYYY-MM-DD/scan.json
"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import core
import backtest as bt

VN = {"BO_L": "Breakout long (vào ngay)", "BD_S_2": "Breakdown short (2 nến)", "PB_L": "Long hồi", "PB_S": "Short hồi",
      "BO_L_alert": "Chờ breakout long", "BD_S_alert": "Chờ breakdown short"}


def expectancy():
    try:
        return json.load(open(core.HERE / "expectancy.json", encoding="utf-8"))
    except Exception:
        return {}


def exp_of(E, setup, btc_up):
    """(kỳ vọng R/tín hiệu, ổn định?, n) của setup trong bối cảnh BTC 4H hiện tại."""
    s = E.get(setup, {}).get("btc_up" if btc_up else "btc_dn")
    if not s or not s.get("n"):
        return None, False, 0
    return s["per_sig"], (s.get("h1") or 0) > 0 and (s.get("h2") or 0) > 0, s["n"]


def detail(sym):
    """Bức tranh khung lớn của 1 coin (dùng cho BTC/ETH và cho báo cáo)."""
    k4 = core.kl(sym, "4h", 300); kd = core.kl(sym, "1d", 150)
    c4 = [x[4] for x in k4]; cd = [x[4] for x in kd]; p = c4[-1]
    tk, kj, ctop, cbot, _ = core.ichimoku(k4); ph, pl = core.pivots(k4[-60:])
    f = lambda t, fmt: datetime.fromtimestamp(t, timezone.utc).strftime(fmt)
    return dict(sym=sym[:-4], p=p, atr=core.atr_k(k4), atrp=round(core.atr_k(k4) / p * 100, 2),
                e34=core.ema(c4, 34), e89=core.ema(c4, 89), e200=core.ema(c4, 200), e34d=core.ema(cd, 34), e89d=core.ema(cd, 89),
                tenkan=tk, kijun=kj, ctop=ctop, cbot=cbot, rsi4=round(core.rsi(c4)), rsid=round(core.rsi(cd)),
                t4="UP" if core.ema(c4, 34) > core.ema(c4, 89) else "DN", t1=core.trend(cd),
                hi30=max(x[2] for x in k4[-31:-1]), lo30=min(x[3] for x in k4[-31:-1]), piv_hi=ph[-3:], piv_lo=pl[-3:],
                chg7=round((cd[-1] / cd[-8] - 1) * 100, 1),
                last4h=[(f(x[0], "%d %Hh"), x[1], x[2], x[3], x[4]) for x in k4[-7:]],
                last1d=[(f(x[0], "%d/%m"), x[1], x[2], x[3], x[4]) for x in kd[-5:]])


def scan(t, btc7):
    sym = t["symbol"]; vol = float(t["quoteVolume"])
    try:
        k4 = core.kl(sym, "4h", 300); kd = core.kl(sym, "1d", 150)
    except Exception:
        return None
    if len(k4) < 200 or len(kd) < 100:
        return dict(sym=sym[:-4], rejected=["thiếu dữ liệu (coin quá mới)"], vol=round(vol / 1e6))
    ok, why, tr = core.quality(sym, k4, kd, vol)
    p = k4[-1][4]; S = bt.prep(k4[:-1], kd[:-1]); i = S["n"] - 1; A = S["atr"][i]
    cd = [x[4] for x in kd]
    base = dict(sym=sym[:-4], p=p, vol=round(vol / 1e6), tier=tr, atrp=round(A / p * 100, 2), t4="UP" if S["e34"][i] > S["e89"][i] else "DN",
                t1=S["dtr"][i], rsi4=round(core.rsi(S["c"])), rs7=round(((cd[-1] / cd[-8]) / btc7 - 1) * 100, 1), kijun=S["kij"][i], e34=S["e34"][i])
    if not ok:
        return dict(base, rejected=why)
    out = []
    h, l, c, o, v = S["h"], S["l"], S["c"], S["o"], S["v"]

    def add(setup, side, entry, stop, level, state, note):
        R = abs(entry - stop); sg = 1 if side == "long" else -1
        out.append(dict(base, setup=setup, side=side, state=state, level=level, entry=entry, stop=stop, tp1=entry + sg * 1.5 * R,
                        tp2=entry + sg * 2.5 * R, risk=round(R / entry * 100, 2), ext=round(sg * (p - level) / A, 2) if level else None, note=note))

    # --- tín hiệu đã xác nhận ở nến i (đúng định nghĩa backtest)
    names = {x[0]: x for x in bt_candidates_live(S, i)}
    if "BO_L" in names:
        _, _, _, _, st = names["BO_L"]; top = max(h[i - 33:i - 3])
        add("BO_L", "long", p, st, top, "VÀO NGAY" if p - top <= 1.0 * A else "ĐÃ CHẠY XA (không đuổi)",
            f"nến 4H vừa đóng {c[i]:.6g} > đỉnh nền {top:.6g}, vol {v[i] / (sum(v[i - 33:i - 3]) / 30):.1f}x")
    if "PB_L" in names:
        add("PB_L", "long", p, min(min(l[i - 5:i + 1]) - 0.3 * A, p - A), None, "XÁC NHẬN", "chạm EMA34/Kijun 4H rồi đóng xanh trên EMA34 (1D tăng, 4H tăng)")
    if "PB_S" in names:
        add("PB_S", "short", p, max(max(h[i - 5:i + 1]) + 0.3 * A, p + A), None, "XÁC NHẬN", "hồi lên EMA34/Kijun 4H rồi đóng đỏ dưới EMA34 (4H giảm)")
    # --- breakdown short: 1/2 hoặc 2/2
    for back, state in ((0, "1/2 CHỜ NẾN KẾ"), (1, "2/2 VÀO")):
        j = i - back
        bot = min(l[j - 33:j - 3]); top = max(h[j - 33:j - 3]); w = (top - bot) / bot; va = sum(v[j - 33:j - 3]) / 30
        if 0.03 <= w <= 0.30 and v[j] >= 1.5 * va and c[j] < bot and S["dtr"][j] != "UP" and all(c[x] < bot for x in range(j, i + 1)):
            st = max(bot + S["atr"][j], (top + bot) / 2)
            if p < st:
                add("BD_S_2", "short", p, st, bot, state if bot - p <= 1.0 * A else "ĐÃ CHẠY XA (không đuổi)",
                    f"đóng dưới đáy nền {bot:.6g}, vol {v[j] / va:.1f}x" + (" — nến kế tiếp cũng đóng dưới" if back else ""))
            break
    # --- sắp phá mốc (đặt alert chờ nến 4H đóng)
    hi = max(h[i - 29:i + 1]); lo = min(l[i - 29:i + 1]); w = (hi - lo) / lo
    if 0.03 <= w <= 0.30 and not any(x["setup"] in ("BO_L", "BD_S_2") for x in out):
        if 0 <= hi - p <= 1.0 * A and S["dtr"][i] != "DN":
            add("BO_L_alert", "long", hi, min(hi - A, (hi + lo) / 2), hi, "CHỜ 4H ĐÓNG TRÊN", f"cách đỉnh 30 nến {hi:.6g} {(hi - p) / A:.1f} ATR")
        if 0 <= p - lo <= 1.0 * A and S["dtr"][i] != "UP":
            add("BD_S_alert", "short", lo, max(lo + A, (hi + lo) / 2), lo, "CHỜ 2 NẾN 4H ĐÓNG DƯỚI", f"cách đáy 30 nến {lo:.6g} {(p - lo) / A:.1f} ATR")
    return dict(base, setups=out)


def bt_candidates_live(S, i):
    """backtest.candidates cần o[i+1] (giá mở nến kế) — ở live chưa có nên mượn giá đóng nến i."""
    S2 = dict(S); S2["o"] = S["o"] + [S["c"][i]]; S2["n"] = S["n"]
    try:
        return bt.candidates(S2, i)
    except IndexError:
        return []


def run(extra=()):
    E = expectancy(); reg = core.regime()
    U = core.universe(120, min_vol=0, extra=extra)
    U = [t for t in U if float(t["quoteVolume"]) >= 20e6 or t["symbol"][:-4] in {x.upper() for x in extra}]
    bd = [x[4] for x in core.kl("BTCUSDT", "1d", 150)]; btc7 = bd[-1] / bd[-8]
    with ThreadPoolExecutor(10) as ex:
        R = [r for r in ex.map(lambda t: scan(t, btc7), U) if r]
    setups = [s for r in R for s in r.get("setups", [])]
    for s in setups:
        s["exp"], s["stable"], s["exp_n"] = exp_of(E, s["setup"], reg["btc_up"])
    setups.sort(key=lambda s: (-(s["exp"] if s["exp"] is not None else -9), s["tier"], -s["rs7"] if s["side"] == "long" else s["rs7"]))
    rejected = [dict(sym=r["sym"], vol=r.get("vol"), why=r["rejected"]) for r in R if r.get("rejected")]
    table = [{k: r[k] for k in ("sym", "p", "vol", "tier", "atrp", "t4", "t1", "rsi4", "rs7")} for r in R if "setups" in r]
    return dict(time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), regime=reg, btc=detail("BTCUSDT"), eth=detail("ETHUSDT"),
                expectancy_meta=E.get("_meta"), setups=setups, coins=table, rejected=rejected)


def fmt(x):
    return f"{x:,.0f}" if x >= 1000 else f"{x:.6g}"


if __name__ == "__main__":
    D = run([x.upper() for x in sys.argv[1:]])
    json.dump(D, open(core.outdir() / "scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    g = D["regime"]
    print(f"{D['time']} | Top {g['n']}: 4H tăng {g['up4']}/{g['n']} ({g['breadth4'] * 100:.0f}%) · 1D tăng {g['up1']}/{g['n']} ({g['breadth1'] * 100:.0f}%) "
          f"→ {g['mode']} | BTC 4H {'TĂNG' if g['btc_up'] else 'GIẢM'}")
    for k in ("btc", "eth"):
        d = D[k]
        print(f"{d['sym']}: {fmt(d['p'])} | 4H {d['t4']} EMA34 {fmt(d['e34'])} EMA89 {fmt(d['e89'])} Kijun {fmt(d['kijun'])} mây {fmt(d['cbot'])}–{fmt(d['ctop'])} RSI {d['rsi4']} "
              f"ATR {d['atrp']}% | 1D {d['t1']} EMA34 {fmt(d['e34d'])} EMA89 {fmt(d['e89d'])} RSI {d['rsid']} | range30 {fmt(d['lo30'])}–{fmt(d['hi30'])} | 7d {d['chg7']:+}%")
    m = D["expectancy_meta"] or {}
    print(f"\nKỳ vọng R theo backtest {m.get('start')}–{m.get('end')} (chạy {m.get('run')}), bối cảnh BTC 4H {'tăng' if g['btc_up'] else 'giảm'}. "
          "'ổn định' = dương ở cả 2 nửa giai đoạn.")
    for setup in ("BO_L", "BD_S_2", "PB_L", "PB_S", "BO_L_alert", "BD_S_alert"):
        rows = [s for s in D["setups"] if s["setup"] == setup]
        if not rows:
            continue
        e = rows[0]
        ex = "chưa có số" if e["exp"] is None else f"{e['exp']:+.2f}R/tín hiệu, {'ổn định' if e['stable'] else 'KHÔNG ổn định'}, n={e['exp_n']}"
        print(f"\n=== {VN[setup]} [{setup}] — kỳ vọng {ex} ({len(rows)}) ===")
        for s in rows:
            print(f"[{s['tier']}] {s['sym']:9} {s['state']:24} p={fmt(s['p']):<10} mốc {fmt(s['level']) if s['level'] else '-':<10} entry {fmt(s['entry']):<10} "
                  f"STL {fmt(s['stop']):<10} ({s['risk']}%) TP {fmt(s['tp1'])}/{fmt(s['tp2'])} | 4H {s['t4']} 1D {s['t1']} RSI {s['rsi4']} RS7 {s['rs7']:+} "
                  f"ATR {s['atrp']}% vol {s['vol']}M | {s['note']}")
    print(f"\nBị loại bởi bộ lọc chất lượng ({len(D['rejected'])}): " + "; ".join(f"{r['sym']} ({r['why'][0]})" for r in D["rejected"][:40]))
    longs_ok = [s for s in D["setups"] if s["side"] == "long" and s["setup"] in ("BO_L", "PB_L") and s["state"] in ("VÀO NGAY", "XÁC NHẬN") and (s["exp"] or 0) > 0]
    print("\nLệnh BUY hiện tại: " + ("KHÔNG CÓ (BTC 4H giảm → mặc định không buy; kèo long bên trên chỉ để theo dõi)" if not g["btc_up"]
                                      else "không có" if not longs_ok else "xem nhóm BO_L/PB_L — chỉ là ứng viên, CHƯA BUY cho tới khi có ✅"))
