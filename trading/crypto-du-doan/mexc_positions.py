"""Đọc vị thế MEXC Futures (CHỈ ĐỌC) -> in bảng + ghi positions_mexc.json (không chứa key).

Cách dùng (bạn tự chạy trên máy):
  1. Tạo API key trên MEXC chỉ bật quyền XEM (Futures: View / Read). KHÔNG bật Trade, KHÔNG bật Withdraw.
  2. Copy mexc_config.example.json -> mexc_config.json, điền api_key / api_secret.
     (hoặc đặt biến môi trường MEXC_API_KEY, MEXC_API_SECRET)
  3. Chạy:  python mexc_positions.py             -> đọc 1 lần
            python mexc_positions.py --watch 60  -> cập nhật mỗi 60 giây (Ctrl+C để dừng)

STL/TP lấy từ lệnh TP/SL đang đặt trên sàn; nếu chưa đặt thì lấy từ ve_plan.json (kế hoạch đã bàn).
Script chỉ gọi các endpoint GET để đọc dữ liệu, không có hàm nào đặt hoặc huỷ lệnh.
"""
import hashlib, hmac, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
BASE = "https://contract.mexc.com"
OUT = HERE / datetime.now().strftime("%Y-%m-%d") / "positions_mexc.json"
OUT.parent.mkdir(exist_ok=True)


def load_keys():
    key, sec = os.environ.get("MEXC_API_KEY"), os.environ.get("MEXC_API_SECRET")
    cfg = HERE / "mexc_config.json"
    if not (key and sec) and cfg.exists():
        c = json.loads(cfg.read_text(encoding="utf-8"))
        key, sec = c.get("api_key"), c.get("api_secret")
    if not (key and sec) or "DIEN_" in (key + sec):
        sys.exit("Chưa có API key. Tạo mexc_config.json từ mexc_config.example.json (key chỉ quyền đọc).")
    return key.strip(), sec.strip()


def http_get(path, params=None, keys=None):
    params = {k: v for k, v in (params or {}).items() if v is not None}
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
    if keys:
        ts = str(int(time.time() * 1000))
        sig = hmac.new(keys[1].encode(), (keys[0] + ts + qs).encode(), hashlib.sha256).hexdigest()
        headers.update({"ApiKey": keys[0], "Request-Time": ts, "Signature": sig})
    url = BASE + path + ("?" + qs if qs else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        j = json.load(r)
    if not j.get("success", True) or j.get("code", 0) not in (0, 200):
        raise RuntimeError(f"{path}: code={j.get('code')} msg={j.get('message') or j.get('msg')}")
    return j.get("data")


_detail = {}
def contract_size(sym):
    if sym not in _detail:
        _detail[sym] = float(http_get("/api/v1/contract/detail", {"symbol": sym})["contractSize"])
    return _detail[sym]


def read_once(keys):
    plan = {}
    if (HERE / "ve_plan.json").exists():
        plan = json.loads((HERE / "ve_plan.json").read_text(encoding="utf-8"))
    pos = http_get("/api/v1/private/position/open_positions", keys=keys) or []
    try:
        stops = http_get("/api/v1/private/stoporder/list/orders",
                         {"is_finished": 0, "page_num": 1, "page_size": 100}, keys=keys) or []
        if isinstance(stops, dict):
            stops = stops.get("resultList", [])
    except Exception as e:
        stops, _ = [], print("  (không đọc được lệnh TP/SL trên sàn:", e, ")")
    sl_by_pos = {str(s.get("positionId")): s for s in stops}
    equity = None
    try:
        for a in http_get("/api/v1/private/account/assets", keys=keys) or []:
            if a.get("currency") == "USDT":
                equity = float(a.get("equity") or 0)
    except Exception:
        pass

    rows, total_risk, total_pnl = [], 0.0, 0.0
    for p in pos:
        sym = p["symbol"]
        side = 1 if int(p["positionType"]) == 1 else -1
        cs = contract_size(sym)
        qty = float(p["holdVol"]) * cs
        avg = float(p.get("holdAvgPrice") or p.get("openAvgPrice"))
        tk = http_get("/api/v1/contract/ticker", {"symbol": sym})
        mark = float(tk.get("fairPrice") or tk["lastPrice"])
        pnl = (mark - avg) * qty * side
        s = sl_by_pos.get(str(p.get("positionId")), {})
        pl = plan.get(sym, {})
        stl = float(s.get("stopLossPrice") or 0) or pl.get("stl")
        tps = [float(s["takeProfitPrice"])] if s.get("takeProfitPrice") else pl.get("tp", [])
        stl_src = "sàn" if s.get("stopLossPrice") else ("kế hoạch" if pl.get("stl") else "CHƯA CÓ")
        risk = abs(avg - stl) * qty if stl else None
        r_mult = pnl / risk if risk else None
        dist_stl = (mark - stl) / mark * 100 * side if stl else None
        total_pnl += pnl
        total_risk += (max(0.0, (avg - stl) * qty * side) if stl else 0.0)
        rows.append(dict(symbol=sym, side="LONG" if side == 1 else "SHORT", qty=round(qty, 8), entry=avg,
                         mark=mark, pnl_usdt=round(pnl, 4), pnl_pct=round((mark / avg - 1) * 100 * side, 2),
                         leverage=p.get("leverage"), margin=float(p.get("im") or 0), liq=float(p.get("liquidatePrice") or 0),
                         stl=stl, stl_source=stl_src, dist_to_stl_pct=round(dist_stl, 2) if dist_stl is not None else None,
                         risk_usdt=round(risk, 4) if risk else None, r_multiple=round(r_mult, 2) if r_mult is not None else None,
                         tp=tps))
    out = dict(time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), equity_usdt=equity, positions=rows,
               total_unrealized_pnl=round(total_pnl, 4), total_loss_if_all_stl=round(total_risk, 4),
               total_loss_if_all_stl_pct=round(total_risk / equity * 100, 2) if equity else None)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n=== MEXC Futures — {out['time']} — Equity: {equity if equity is not None else '?'} USDT ===")
    print(f"{'Coin':12}{'Lệnh':6}{'Entry':>11}{'Giá':>11}{'L/L %':>8}{'L/L $':>10}{'STL':>11}{'→STL %':>8}{'R':>6}  Nguồn STL")
    for r in rows:
        print(f"{r['symbol']:12}{r['side']:6}{r['entry']:>11g}{r['mark']:>11g}{r['pnl_pct']:>+8.2f}{r['pnl_usdt']:>+10.2f}"
              f"{(r['stl'] or 0):>11g}{(r['dist_to_stl_pct'] if r['dist_to_stl_pct'] is not None else 0):>8.2f}"
              f"{(r['r_multiple'] if r['r_multiple'] is not None else 0):>+6.2f}  {r['stl_source']}")
    if not rows:
        print("(không có vị thế mở)")
    print(f"Tổng lời/lỗ chưa chốt: {out['total_unrealized_pnl']:+.2f} USDT | Nếu TẤT CẢ dính STL: -{out['total_loss_if_all_stl']:.2f} USDT"
          + (f" ({out['total_loss_if_all_stl_pct']}% tài khoản)" if out['total_loss_if_all_stl_pct'] is not None else ""))
    print(f"Đã ghi {OUT.name} (không chứa API key).")


if __name__ == "__main__":
    keys = load_keys()
    every = int(sys.argv[sys.argv.index("--watch") + 1]) if "--watch" in sys.argv else 0
    while True:
        try:
            read_once(keys)
        except Exception as e:
            print("LỖI:", e, "\n→ Kiểm tra: key đúng, đã bật quyền Futures View (đọc), IP được phép, đồng hồ máy đúng giờ.")
        if not every:
            break
        time.sleep(every)
