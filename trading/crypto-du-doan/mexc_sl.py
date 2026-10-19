"""Gắn STOP-LOSS (và TP nếu có) cho VỊ THẾ ĐANG MỞ trên MEXC Futures — BẠN tự chạy, BẠN tự xác nhận.

Mức SL lấy từ file YYYY-MM-DD/sl_plan.json (thư mục ngày mới nhất), dạng:
  {"TRUMPOFFICIAL_USDT": {"stop": 1.853, "tp": null}}
Dùng:  python mexc_sl.py          -> xem vị thế + SL định gắn, gõ Y từng vị thế để gửi (CLI hỏi Confirm thêm lần nữa)
       python mexc_sl.py --plan   -> chỉ xem, không gửi
"""
import json, os, subprocess, sys, tempfile, urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent


class _Tee:
    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8"); self.out = sys.stdout
    def write(self, s):
        self.out.write(s); self.f.write(s); self.f.flush()
    def flush(self):
        self.out.flush(); self.f.flush()


def ask(prompt):
    a = input(prompt).strip(); print(f"      [bạn gõ: {a!r}]"); return a


def cli_read(args):
    r = subprocess.run("mexc --read-only " + args, shell=True, capture_output=True, text=True, encoding="utf-8")
    d = json.loads(r.stdout or "{}")
    if "error" in d:
        raise RuntimeError(d["error"].get("message"))
    return d.get("data") or []


def pub(path):
    req = urllib.request.Request("https://contract.mexc.com/api/v1/contract" + path, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=15))["data"]


def main():
    day = HERE / datetime.now().strftime("%Y-%m-%d"); day.mkdir(exist_ok=True)
    sys.stdout = _Tee(day / "dat_sl_log.txt")
    print(f"\n######## Chạy lúc {datetime.now():%Y-%m-%d %H:%M:%S} | {' '.join(sys.argv[1:]) or '(không)'} ########")
    plan_only = "--plan" in sys.argv
    plans = sorted(HERE.glob("20??-??-??/sl_plan.json"))
    if not plans:
        print("Không có file YYYY-MM-DD/sl_plan.json"); return
    plan = json.loads(plans[-1].read_text(encoding="utf-8")); print("File SL:", plans[-1].relative_to(HERE))
    pos = cli_read("contract trade open-positions")
    existing = {str(x.get("positionId")): x for x in cli_read("contract trade stoporder-open-orders")}
    todo = []
    for p in pos:
        s = p["symbol"]; long = p["positionType"] == 1
        d = pub(f"/detail?symbol={s}"); t = pub(f"/ticker?symbol={s}")
        cs, ps, last = float(d["contractSize"]), int(d["priceScale"]), float(t["lastPrice"])
        qty = p["holdVol"] * cs; avg = float(p["holdAvgPrice"])
        ex = existing.get(str(p["positionId"]), {})
        cfg = plan.get(s)
        line = (f"\n{s} {'LONG' if long else 'SHORT'} {qty:g} coin @ {avg} | giá {last} | L/L {p['unRealizedPnl']:+.2f} | "
                f"SL hiện có: {ex.get('stopLossPrice') or 'KHÔNG'} TP hiện có: {ex.get('takeProfitPrice') or 'không'}")
        print(line)
        if not cfg:
            print("    → không có trong sl_plan.json, bỏ qua"); continue
        sl = round(float(cfg["stop"]), ps); tp = round(float(cfg["tp"]), ps) if cfg.get("tp") else None
        bad = (long and sl >= last) or ((not long) and sl <= last)
        loss = (avg - sl) * qty if long else (sl - avg) * qty
        print(f"    → gắn SL {sl}" + (f", TP {tp}" if tp else "") + f" | nếu dính SL: {-loss:+.2f} USDT so với giá vào")
        if bad:
            print("    ⚠ SL nằm sai phía so với giá hiện tại (sẽ kích hoạt ngay) — bỏ qua"); continue
        if ex.get("stopLossPrice"):
            print("    ⚠ Vị thế ĐÃ có SL trên sàn. Gửi thêm sẽ tạo lệnh SL thứ hai — sửa SL cũ trên app thì hơn. Bỏ qua.")
            continue
        body = {"positionId": int(p["positionId"]), "stopLossPrice": sl, "vol": p["holdVol"], "lossTrend": 1}
        if tp:
            body.update({"takeProfitPrice": tp, "profitTrend": 1})
        todo.append((s, body))
    if plan_only or not todo:
        print("\n(Chế độ xem / không có gì để gửi)"); return
    for s, body in todo:
        if ask(f"\nGõ Y để gắn SL cho {s}: ").upper() not in ("Y", "YES"):
            print("    → Huỷ."); continue
        fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
        Path(path).write_text(json.dumps(body), encoding="utf-8")
        try:
            rc = subprocess.run(["mexc", "contract", "trade", "stoporder-place-v2", "--data", "@" + path], shell=(os.name == "nt")).returncode
        finally:
            os.remove(path)
        print(f"      [MEXC CLI trả mã {rc}]" + ("" if rc == 0 else " ⚠ KHÔNG thành công — xem lỗi JSON ở trên, KHÔNG tự thử lại"))
    print("\nXong. Nhắn Claude 'kiểm tra lại' để xác nhận SL trên sàn.")


if __name__ == "__main__":
    main()
