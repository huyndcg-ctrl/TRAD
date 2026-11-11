"""Backtest các setup 4H (Binance Futures) — gộp backtest.py + entry_test.py cũ, dùng lõi chung core.py.

Setup (chỉ dùng nến ĐÃ ĐÓNG, vào ở giá mở nến kế tiếp trừ khi ghi khác):
  BO_L        breakout long: đóng trên đỉnh nền 30 nến (bỏ 3 nến cuối), vol ≥1.5x, nền 3–30%, 1D không giảm → VÀO NGAY
  BO_L_retest như trên nhưng chờ retest đỉnh nền trong 6 nến (lỡ thì bỏ)
  BO_L_alert  kiểu alert giá: nến đóng trên đỉnh cao nhất 30 nến gần nhất (không lọc volume) → vào ngay
  BD_S        breakdown short: đóng dưới đáy nền + vol ≥1.5x, 1D không tăng → vào ngay
  BD_S_2      như BD_S nhưng nến kế tiếp cũng phải đóng dưới đáy nền (2 nến) → rồi mới vào
  BD_S_alert  kiểu alert Pine: 2 nến liên tiếp đóng dưới đáy thấp nhất 30 nến (không lọc volume) → vào
  PB_L        long hồi: 1D tăng + 4H tăng, chạm EMA34/Kijun rồi đóng xanh trên EMA34
  PB_S        short hồi: 4H giảm, chạm EMA34/Kijun rồi đóng đỏ dưới EMA34
Quản lý lệnh: 50% chốt 1.5R, 50% chốt 2.5R, hết 40 nến đóng theo giá, phí 0.1%; nến chạm cả SL lẫn TP tính SL.
Bối cảnh: BTC 4H (EMA34>EMA89), độ rộng thị trường (% coin 4H tăng). Kiểm tra ngoài mẫu: chia đôi giai đoạn (nửa đầu / nửa sau).

Chạy: python backtest.py  → in bảng, lưu YYYY-MM-DD/backtest.json và expectancy.json (scan_all.py đọc file này để xếp hạng kèo).
"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import core

N4, ND, FEE, HOLD = 1500, 400, 0.001, 40
SETUPS = ("BO_L", "BO_L_retest", "BO_L_alert", "BD_S", "BD_S_2", "BD_S_alert", "PB_L", "PB_S")


def load(sym):
    K = core.kl(sym, "4h", N4, cache=False)[:-1]; D = core.kl(sym, "1d", ND, cache=False)[:-1]
    return sym, K, D


def prep(K, D):
    t = [x[0] for x in K]; o = [x[1] for x in K]; h = [x[2] for x in K]; l = [x[3] for x in K]; c = [x[4] for x in K]; v = [x[5] for x in K]
    n = len(K)
    e34, e89 = core.ema_series(c, 34), core.ema_series(c, 89)
    atr = core.atr_series(K)
    kij = [(max(h[max(0, i - 25):i + 1]) + min(l[max(0, i - 25):i + 1])) / 2 for i in range(n)]
    dc = [x[4] for x in D]; dt = [x[0] for x in D]
    d34, d89 = core.ema_series(dc, 34), core.ema_series(dc, 89)
    dtrend, j = [], -1                       # trend 1D tại nến 4H i = ngày đã ĐÓNG gần nhất
    for i in range(n):
        close_time = t[i] + 4 * 3600
        while j + 1 < len(dt) and dt[j + 1] + 86400 <= close_time:
            j += 1
        dtrend.append(None if j < 89 else "UP" if d34[j] > d89[j] and dc[j] > d89[j] else "DN" if d34[j] < d89[j] and dc[j] < d89[j] else "MIX")
    return dict(t=t, o=o, h=h, l=l, c=c, v=v, e34=e34, e89=e89, atr=atr, kij=kij, dtr=dtrend, n=n)


def simulate(S, i_entry, side, entry, stop):
    """Trả về (R thực đã trừ phí, chỉ số nến thoát)."""
    R = abs(entry - stop)
    if R <= 0 or i_entry >= S["n"]:
        return None
    long = side == "L"
    if (entry <= stop) if long else (entry >= stop):
        return None
    tp1, tp2 = (entry + 1.5 * R, entry + 2.5 * R) if long else (entry - 1.5 * R, entry - 2.5 * R)
    half1 = None
    for j in range(i_entry, min(i_entry + HOLD, S["n"])):
        hi, lo = S["h"][j], S["l"][j]
        if (lo <= stop) if long else (hi >= stop):               # bảo thủ: SL trước
            res, ex = 0.5 * (half1 if half1 is not None else -1.0) + 0.5 * -1.0, j
            break
        if half1 is None and (hi >= tp1 if long else lo <= tp1):
            half1 = 1.5
        if half1 is not None and (hi >= tp2 if long else lo <= tp2):
            res, ex = 0.5 * half1 + 0.5 * 2.5, j
            break
    else:
        j = min(i_entry + HOLD, S["n"]) - 1
        rem = ((S["c"][j] - entry) if long else (entry - S["c"][j])) / R
        res, ex = 0.5 * (half1 if half1 is not None else rem) + 0.5 * rem, j
    return res - FEE * entry / R, ex


def candidates(S, i):
    """Các tín hiệu tại nến đã đóng i → [(setup, side, i_entry, entry, stop)] (i_entry có thể > i+1; None = lỡ lệnh)."""
    n = S["n"]; h, l, c, o, v = S["h"], S["l"], S["c"], S["o"], S["v"]; A = S["atr"][i]; d1 = S["dtr"][i]
    out = []
    up4 = S["e34"][i] > S["e89"][i] and c[i] > S["e89"][i]; dn4 = S["e34"][i] < S["e89"][i] and c[i] < S["e89"][i]
    zoneL = max(S["e34"][i], S["kij"][i]); zoneS = min(S["e34"][i], S["kij"][i])
    if d1 == "UP" and up4 and min(l[i - 2:i + 1]) <= zoneL and c[i] > S["e34"][i] and c[i] > o[i]:
        out.append(("PB_L", "L", i + 1, o[i + 1], min(min(l[i - 5:i + 1]) - 0.3 * A, o[i + 1] - A)))
    if dn4 and max(h[i - 2:i + 1]) >= zoneS and c[i] < S["e34"][i] and c[i] < o[i]:
        out.append(("PB_S", "S", i + 1, o[i + 1], max(max(h[i - 5:i + 1]) + 0.3 * A, o[i + 1] + A)))
    # nền 30 nến bỏ 3 nến cuối + volume
    top = max(h[i - 33:i - 3]); bot = min(l[i - 33:i - 3]); w = (top - bot) / bot; va = sum(v[i - 33:i - 3]) / 30
    if 0.03 <= w <= 0.30 and v[i] >= 1.5 * va:
        mid = (top + bot) / 2
        if c[i] > top and d1 != "DN":
            st = min(top - A, mid)
            out.append(("BO_L", "L", i + 1, o[i + 1], st))
            for j in range(i + 1, min(i + 7, n)):
                if l[j] <= top:
                    out.append(("BO_L_retest", "L", j, min(top, o[j]), st)); break
            else:
                out.append(("BO_L_retest", "L", None, None, None))
        if c[i] < bot and d1 != "UP":
            st = max(bot + A, mid)
            out.append(("BD_S", "S", i + 1, o[i + 1], st))
            if i + 2 < n and c[i + 1] < bot:
                out.append(("BD_S_2", "S", i + 2, o[i + 2], st))
            else:
                out.append(("BD_S_2", "S", None, None, None))
    # kiểu alert: mốc = đỉnh/đáy 30 nến gần nhất (tính cả 3 nến cuối), không lọc volume
    hi = max(h[i - 30:i]); lo = min(l[i - 30:i]); w2 = (hi - lo) / lo
    if 0.03 <= w2 <= 0.30 and c[i] > hi and d1 != "DN":
        out.append(("BO_L_alert", "L", i + 1, o[i + 1], min(hi - A, (hi + lo) / 2)))
    lo2 = min(l[i - 31:i - 1]); hi2 = max(h[i - 31:i - 1]); w3 = (hi2 - lo2) / lo2
    if 0.03 <= w3 <= 0.30 and c[i] < lo2 and c[i - 1] < lo2 and c[i - 2] >= lo2 and d1 != "UP":
        out.append(("BD_S_alert", "S", i + 1, o[i + 1], max(lo2 + A, (hi2 + lo2) / 2)))
    return out


def run(sym, S, btc_up, breadth):
    out = []; busy = {}
    for i in range(120, S["n"] - 2):
        t = S["t"][i]
        for name, side, ie, ent, stop in candidates(S, i):
            if busy.get(name, -1) >= i:
                continue
            if ie is None:
                busy[name] = i + 6; out.append(dict(sym=sym, setup=name, t=t, r=None, btc=btc_up.get(t), br=breadth.get(t))); continue
            r = simulate(S, ie, side, ent, stop)
            if r is None:
                continue
            busy[name] = r[1]
            out.append(dict(sym=sym, setup=name, t=t, r=r[0], btc=btc_up.get(t), br=breadth.get(t), risk=abs(ent - stop) / ent * 100))
    return out


def stats(T):
    """T: các tín hiệu (r=None là lỡ lệnh). avgR tính trên lệnh khớp; per_sig tính trên mọi tín hiệu (lỡ = 0R)."""
    rs = [x["r"] for x in T if x["r"] is not None]
    if not rs:
        return dict(n=0, sig=len(T))
    w = [r for r in rs if r > 0]; lo = [r for r in rs if r <= 0]
    eq = pk = dd = 0
    for x in sorted((x for x in T if x["r"] is not None), key=lambda x: x["t"]):
        eq += x["r"]; pk = max(pk, eq); dd = min(dd, eq - pk)
    return dict(n=len(rs), sig=len(T), win=round(len(w) / len(rs) * 100, 1), avgR=round(sum(rs) / len(rs), 3),
                per_sig=round(sum(rs) / len(T), 3), pf=round(sum(w) / abs(sum(lo)), 2) if lo and sum(lo) else None,
                totR=round(sum(rs), 1), maxDD=round(dd, 1))


def build(nsym=40):
    syms = [t["symbol"] for t in sorted(core.tickers(), key=lambda t: -float(t["quoteVolume"]))[:nsym]]
    if "BTCUSDT" not in syms:
        syms.append("BTCUSDT")
    with ThreadPoolExecutor(8) as ex:
        data = {s: prep(K, D) for s, K, D in ex.map(load, syms) if len(K) > 300 and len(D) > 120}
    B = data["BTCUSDT"]
    btc_up = {B["t"][i]: B["e34"][i] > B["e89"][i] for i in range(B["n"])}
    cnt = {}
    for S in data.values():
        for i in range(S["n"]):
            a = cnt.setdefault(S["t"][i], [0, 0]); a[0] += S["e34"][i] > S["e89"][i]; a[1] += 1
    breadth = {t: a[0] / a[1] for t, a in cnt.items() if a[1] >= 20}
    T = []
    for s, S in data.items():
        T += run(s, S, btc_up, breadth)
    return data, T


CTX = {"all": lambda x: True, "btc_up": lambda x: x["btc"] is True, "btc_dn": lambda x: x["btc"] is False,
       "br_hi": lambda x: x["br"] is not None and x["br"] >= 0.5, "br_lo": lambda x: x["br"] is not None and x["br"] < 0.5}
CTX_VN = {"all": "tất cả", "btc_up": "BTC 4H tăng", "btc_dn": "BTC 4H giảm", "br_hi": "độ rộng ≥50%", "br_lo": "độ rộng <50%"}

if __name__ == "__main__":
    data, T = build()
    ts = sorted(x["t"] for x in T); tmid = ts[len(ts) // 2]
    f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%d/%m/%Y")
    print(f"Coin: {len(data)} | Giai đoạn: {f(ts[0])} → {f(ts[-1])} (chia đôi tại {f(tmid)}) | Tín hiệu: {len(T)}")
    E = dict(_meta=dict(run=datetime.now().strftime("%Y-%m-%d"), coins=len(data), start=f(ts[0]), end=f(ts[-1]), split=f(tmid)))
    for name in SETUPS:
        sub = [x for x in T if x["setup"] == name]; E[name] = {}
        print(f"\n=== {name} ===")
        for k, fn in CTX.items():
            s = [x for x in sub if fn(x)]; st = stats(s)
            h1 = stats([x for x in s if x["t"] < tmid]); h2 = stats([x for x in s if x["t"] >= tmid])
            st["h1"], st["h2"] = h1.get("per_sig"), h2.get("per_sig"); st["n1"], st["n2"] = h1.get("n", 0), h2.get("n", 0)
            E[name][k] = st
            if st["n"]:
                miss = st["sig"] - st["n"]
                print(f"  {CTX_VN[k]:14} lệnh {st['n']:4} (lỡ {miss:3}) win {st['win']:5}% | TB/lệnh {st['avgR']:+.3f}R | TB/tín hiệu {st['per_sig']:+.3f}R | PF {st['pf']} "
                      f"| DD {st['maxDD']}R | nửa đầu {st['h1']} (n={st['n1']}) · nửa sau {st['h2']} (n={st['n2']})")
    od = core.outdir()
    json.dump(dict(summary=E, trades=T), open(od / "backtest.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(E, open(core.HERE / "expectancy.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nLưu:", od.name + "/backtest.json", "+ expectancy.json")
