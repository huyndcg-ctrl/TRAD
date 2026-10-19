"""HUỶ LỆNH CHỜ (limit) trên MEXC Futures — BẠN tự chạy, BẠN tự xác nhận.

Lệnh cần huỷ lấy từ YYYY-MM-DD/cancel_plan.json (thư mục ngày mới nhất), dạng:
  {"externalOid_prefix": ["vdd_AVAX_L_261012104051"], "note": "..."}
Dùng:  python mexc_cancel.py          -> liệt kê lệnh khớp, gõ Y để huỷ (CLI hỏi Confirm thêm lần nữa)
       python mexc_cancel.py --plan   -> chỉ xem
"""
import json, os, subprocess, sys, tempfile
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


def main():
    day = HERE / datetime.now().strftime("%Y-%m-%d"); day.mkdir(exist_ok=True)
    sys.stdout = _Tee(day / "huy_lenh_log.txt")
    print(f"\n######## Chạy lúc {datetime.now():%Y-%m-%d %H:%M:%S} | {' '.join(sys.argv[1:]) or '(không)'} ########")
    plans = sorted(HERE.glob("20??-??-??/cancel_plan.json"))
    if not plans:
        print("Không có file YYYY-MM-DD/cancel_plan.json"); return
    plan = json.loads(plans[-1].read_text(encoding="utf-8")); print("File huỷ:", plans[-1].relative_to(HERE), "|", plan.get("note", ""))
    pref = tuple(plan.get("externalOid_prefix", []))
    r = subprocess.run("mexc --read-only contract trade open-orders-v2 --page_num 1 --page_size 100", shell=True,
                       capture_output=True, text=True, encoding="utf-8")
    d = json.loads(r.stdout or "{}").get("data") or []
    d = d.get("resultList", d) if isinstance(d, dict) else d
    todo = [o for o in d if pref and str(o.get("externalOid", "")).startswith(pref)]
    print(f"Lệnh chờ đang có: {len(d)} | khớp danh sách huỷ: {len(todo)}")
    for o in todo:
        print(f"   {o['symbol']} {'LONG' if o['side'] == 1 else 'SHORT' if o['side'] == 3 else o['side']} giá {o['price']} vol {o['vol']} "
              f"SL {o.get('stopLossPrice')} TP {o.get('takeProfitPrice')} | {o.get('externalOid')} (id {o['orderId']})")
    if not todo or "--plan" in sys.argv:
        print("(Chế độ xem / không có gì để huỷ)"); return
    a = input(f"\nGõ Y để HUỶ {len(todo)} lệnh trên: ").strip(); print(f"      [bạn gõ: {a!r}]")
    if a.upper() not in ("Y", "YES"):
        print("    → Không huỷ."); return
    fd, path = tempfile.mkstemp(suffix=".json"); os.close(fd)
    Path(path).write_text(json.dumps([int(o["orderId"]) for o in todo]), encoding="utf-8")
    try:
        rc = subprocess.run(["mexc", "contract", "trade", "cancel", "--data", "@" + path], shell=(os.name == "nt")).returncode
    finally:
        os.remove(path)
    print(f"      [MEXC CLI trả mã {rc}]" + ("" if rc == 0 else " ⚠ KHÔNG thành công — xem lỗi ở trên"))
    print("\nXong. Nhắn Claude 'kiểm tra' để xác nhận.")


if __name__ == "__main__":
    main()
