"""Đặt lệnh limit + SL/TP lên MEXC Futures theo file setups_*.json — BẠN tự chạy, BẠN tự xác nhận từng lệnh.

Dùng:  python mexc_entry.py                 -> menu chọn kèo, xác nhận YES từng lệnh rồi gửi
       python mexc_entry.py --plan          -> chỉ in kế hoạch (khối lượng, ký quỹ, lỗ/lãi), không gọi CLI
       python mexc_entry.py --dry-run       -> gọi MEXC CLI với --dry-run (xem request), KHÔNG gửi lệnh
       python mexc_entry.py --file 2026-10-07/setups.json   -> dùng file kèo khác
       (mặc định: setups.json trong thư mục ngày mới nhất)

Mỗi kèo được chia thành nhiều lệnh limit (mặc định 2: TP1/TP2; hoặc theo 'tps'), tất cả gắn cùng STL.
Script KHÔNG dùng --yes: sau khi bạn gõ YES, MEXC CLI vẫn hỏi Confirm/Cancel lần nữa.
"""
import json, math, os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ============ CẤU HÌNH — sửa theo ý bạn ============
RISK_USDT = 10.0     # số USDT chấp nhận mất nếu dính STL (cho 1 kèo size 1.0; kèo size 0.5 = một nửa)
LEVERAGE = 10        # đòn bẩy
OPEN_TYPE = 1        # 1 = isolated (mỗi lệnh ký quỹ riêng — an toàn hơn), 2 = cross
# ====================================================

HERE = Path(__file__).resolve().parent
PUB = "https://contract.mexc.com/api/v1/contract"


def pub(path):
    req = urllib.request.Request(PUB + path, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=15))["data"]


def rnd(x, scale):
    return float(f"{x:.{scale}f}")


def btc_last_closed_1h():
    k = pub("/kline/BTC_USDT?interval=Min60")
    return float(k["close"][-2])          # nến 1H cuối cùng ĐÃ ĐÓNG


def build(s, btc_close, trigger):
    """Tuỳ chọn mỗi kèo (không bắt buộc):
       notional: giá trị lệnh (USDT) thay cho tính theo RISK_USDT | leverage | open_type: "cross"/"isolated"
       tps: [[giá, tỷ lệ], ...] nhiều mức TP (mặc định tp1/tp2 chia theo tp1_ratio)"""
    d = pub(f"/detail?symbol={s['symbol']}")
    t = pub(f"/ticker?symbol={s['symbol']}")
    last = float(t["lastPrice"]); ps = int(d["priceScale"]); cs = float(d["contractSize"]); minv = int(d["minVol"])
    lev = int(s.get("leverage", LEVERAGE)); ot = {"cross": 2, "isolated": 1}.get(s.get("open_type"), OPEN_TYPE)
    side = s["side"]; long = side == "long"
    entry, stop = rnd(s["entry"], ps), rnd(s["stop"], ps)
    tps = [(rnd(x[0], ps), float(x[1])) for x in s["tps"]] if s.get("tps") else           [(rnd(s["tp1"], ps), float(s.get("tp1_ratio", 0.5))), (rnd(s["tp2"], ps), 1 - float(s.get("tp1_ratio", 0.5)))]
    issues = []
    tpp = [x[0] for x in tps]
    if long and not (stop < entry < min(tpp)): issues.append("thứ tự giá long sai (cần STL < entry < các TP)")
    if not long and not (stop > entry > max(tpp)): issues.append("thứ tự giá short sai (cần STL > entry > các TP)")
    if long and entry >= last: issues.append(f"entry {entry} >= giá hiện tại {last}: lệnh limit long sẽ khớp NGAY như market")
    if not long and entry <= last: issues.append(f"entry {entry} <= giá hiện tại {last}: lệnh limit short sẽ khớp NGAY như market")
    if long and stop >= last: issues.append("giá đã ở dưới STL — kèo hỏng")
    if not long and stop <= last: issues.append("giá đã ở trên STL — kèo hỏng")
    btc_ok = (not s.get("need_btc")) or (btc_close is not None and btc_close > trigger)
    if s.get("notional"):
        vol = math.floor(float(s["notional"]) / entry / cs)
    else:
        vol = math.floor(RISK_USDT * float(s.get("size", 1.0)) / abs(entry - stop) / cs)
    if vol < max(len(tps), minv): issues.append(f"khối lượng quá nhỏ ({vol} hợp đồng)")
    vols = [max(1, round(vol * r)) for _, r in tps[:-1]]; vols.append(vol - sum(vols))
    if vols[-1] < 1: issues.append("chia khối lượng TP lỗi")
    notional = vol * cs * entry
    orders = []
    for i, ((tp, _), v) in enumerate(zip(tps, vols), 1):
        orders.append({"symbol": s["symbol"], "price": entry, "vol": v, "leverage": lev, "side": 1 if long else 3,
                       "type": 1, "openType": ot, "stopLossPrice": stop, "takeProfitPrice": tp,
                       "externalOid": f"vdd_{s['symbol'].split('_')[0]}_{side[0].upper()}_{time.strftime('%y%m%d%H%M%S')}_{int(entry * 1000) % 100000}_{i}"})
    loss = vol * cs * abs(entry - stop)
    gain = sum(v * cs * abs(tp - entry) for (tp, _), v in zip(tps, vols))
    return dict(s=s, last=last, entry=entry, stop=stop, tps=tpp, vol=vol, cs=cs, notional=notional, lev=lev, ot=ot,
                margin=notional / lev, loss=loss, gain=gain, rr=gain / loss if loss else 0,
                orders=orders, issues=issues, btc_ok=btc_ok)


def show(i, p):
    s = p["s"]; flag = "✅ SẴN SÀNG" if not p["issues"] and p["btc_ok"] else ("⏳ CHỜ BTC" if not p["issues"] else "❌ KHÔNG ĐẶT ĐƯỢC")
    print(f"\n[{i}] {s['symbol']} {s['side'].upper()} — {flag}   ({s.get('note','')})")
    print(f"    giá hiện {p['last']} | entry {p['entry']} | STL {p['stop']} | TP {' / '.join(str(x) for x in p['tps'])}")
    print(f"    khối lượng {p['vol']} hợp đồng = {p['vol']*p['cs']:g} coin ≈ {p['notional']:.1f} USDT | ký quỹ ≈ {p['margin']:.1f} USDT ({p['lev']}x, {'isolated' if p['ot']==1 else 'CROSS'})")
    print(f"    nếu dính STL: -{p['loss']:.2f} USDT | nếu chạm hết TP: +{p['gain']:.2f} USDT (R:R {p['rr']:.1f})")
    print(f"    chia {len(p['orders'])} lệnh: " + ", ".join(f"{o['vol']} hđ → TP {o['takeProfitPrice']}" for o in p['orders']))
    for x in p["issues"]:
        print("    ⚠", x)


def send(order, dry):
    fd, path = tempfile.mkstemp(suffix=".json", prefix="mexc_order_"); os.close(fd)
    Path(path).write_text(json.dumps(order), encoding="utf-8")
    cmd = ["mexc", "contract", "trade", "create", "--data", "@" + path] + (["--dry-run"] if dry else [])
    try:
        r = subprocess.run(cmd, shell=(os.name == "nt"))       # stdin/stdout của terminal -> CLI tự hỏi Confirm
        return r.returncode
    finally:
        os.remove(path)


class _Tee:
    """In ra màn hình + ghi vào log của ngày (để Claude đọc lại được khi bạn chạy ở cửa sổ riêng)."""
    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8"); self.out = sys.stdout
    def write(self, s):
        self.out.write(s); self.f.write(s); self.f.flush()
    def flush(self):
        self.out.flush(); self.f.flush()


def ask(prompt):
    ans = input(prompt).strip()
    print(f"      [bạn gõ: {ans!r}]")
    return ans


def main():
    from datetime import datetime
    day = HERE / datetime.now().strftime("%Y-%m-%d"); day.mkdir(exist_ok=True)
    sys.stdout = _Tee(day / "dat_lenh_log.txt")
    print(f"\n######## Chạy lúc {datetime.now():%Y-%m-%d %H:%M:%S} | tham số: {' '.join(sys.argv[1:]) or '(không)'} ########")
    plan_only = "--plan" in sys.argv; dry = "--dry-run" in sys.argv
    import shutil
    if not plan_only and not shutil.which("mexc"):
        print("❌ Không tìm thấy lệnh 'mexc' (MEXC CLI). Cài/đưa vào PATH rồi chạy lại.")
        return
    if "--file" in sys.argv:
        fpath = HERE / sys.argv[sys.argv.index("--file") + 1]
    else:  # mặc định: setups.json trong thư mục ngày mới nhất (vd 2026-10-06/setups.json)
        cands = sorted(HERE.glob("20??-??-??/setups.json"))
        if not cands:
            sys.exit("Không tìm thấy file kèo YYYY-MM-DD/setups.json")
        fpath = cands[-1]
    print("File kèo:", fpath.relative_to(HERE))
    cfg = json.loads(fpath.read_text(encoding="utf-8"))
    trig = cfg.get("btc_trigger_long", 0)
    try:
        btc = btc_last_closed_1h()
    except Exception as e:
        btc = None; print("Không đọc được giá BTC:", e)
    print("=" * 78)
    print(f"MEXC ENTRY — rủi ro {RISK_USDT} USDT/kèo, {LEVERAGE}x {'isolated' if OPEN_TYPE==1 else 'cross'}"
          + ("  [CHẾ ĐỘ XEM TRƯỚC — KHÔNG GỬI]" if plan_only or dry else ""))
    print(f"BTC nến 1H đã đóng gần nhất: {btc} | điều kiện long: > {trig} → {'ĐẠT' if btc and btc > trig else 'CHƯA ĐẠT'}")
    plans = []
    for s in cfg["setups"]:
        try:
            plans.append(build(s, btc, trig))
        except Exception as e:
            print("Lỗi đọc", s["symbol"], e)
    for i, p in enumerate(plans, 1):
        show(i, p)
    if plan_only:
        return
    print("\nGõ số kèo muốn đặt (vd: 1,4), hoặc Enter để thoát:")
    pick = ask("> ")
    if not pick:
        print("→ Không chọn kèo nào, thoát."); return
    for k in [int(x) for x in pick.replace(" ", "").split(",") if x.isdigit()]:
        if not 1 <= k <= len(plans):
            print(f"→ Số {k} không có trong danh sách."); continue
        p = plans[k - 1]; show(k, p)
        if p["issues"]:
            print("    → Bỏ qua vì có lỗi ở trên."); continue
        if not p["btc_ok"]:
            if ask("    BTC CHƯA đạt điều kiện long. Vẫn đặt? Gõ FORCE để đặt, Enter để bỏ: ").upper() != "FORCE":
                print("    → Bỏ qua (BTC chưa đạt điều kiện)."); continue
        if ask(f"    Gõ YES để {'XEM (dry-run)' if dry else 'GỬI'} {len(p['orders'])} lệnh của {p['s']['symbol']} (YES/Y): ").upper() not in ("YES", "Y"):
            print("    → Huỷ."); continue
        for o in p["orders"]:
            print(f"    → {o['externalOid']}: {o['vol']} hđ @ {o['price']} SL {o['stopLossPrice']} TP {o['takeProfitPrice']}")
            rc = send(o, dry)
            print(f"      [MEXC CLI trả mã {rc}]")
            if rc != 0:
                why = {10: "CLI cần xác nhận nhưng không hỏi được (cửa sổ không phải terminal tương tác)",
                       1: "lỗi — thường do API key KHÔNG có quyền Trade, sai tham số, hoặc thiếu ký quỹ (xem dòng lỗi JSON ở trên)"}.get(rc, "xem dòng lỗi JSON ở trên")
                print(f"    ⚠ Lệnh KHÔNG thành công: {why}. Dừng kèo này — KHÔNG tự thử lại. Kiểm tra app MEXC.")
                break
    print("\nXong. Kiểm tra lại trên app MEXC hoặc nhắn Claude 'kiểm tra lại'.")


if __name__ == "__main__":
    main()
