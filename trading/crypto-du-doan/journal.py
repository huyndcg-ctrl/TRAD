"""SỔ KÈO: ghi mọi kèo đã báo (từ picks.json) và TỰ CHẤM bằng nến 4H thật (Binance Futures).

  python journal.py add [--file YYYY-MM-DD/picks.json]   thêm kèo của ngày vào journal.json (mặc định picks.json mới nhất)
  python journal.py score                                 chấm lại mọi kèo chưa kết thúc + in bảng "Kèo gần đây vs thực tế"
  python journal.py stats                                 thành tích 7 / 30 ngày theo loại setup

Cách chấm (giống cách alert bắn và giống backtest):
  - Chỉ xét nến 4H đóng SAU lúc kèo được tạo.
  - ✅ vào lệnh khi có `confirm` nến 4H liên tiếp đóng qua `level` (long: trên; short: dưới). Giá vào = giá đóng nến xác nhận.
    Nếu giá vào đã vượt `no_chase` → "không đuổi" (0R).
    Đếm nến liên tiếp tính cả nến trước lúc tạo kèo, nhưng ✅ chỉ bắn ở nến vừa ĐỦ số nến (giống alert), không bắn lại.
    Kèo có `entry_now` = đã ✅ ngay lúc tạo, giá vào = entry_now.
  - Kèo chưa vào mà hôm sau có kèo mới cùng coin → "thay kèo mới" (alert cũ đã bị xoá).
  - Trước khi vào: nến 4H đóng qua `cancel` của kèo, hoặc BTC đóng qua mốc huỷ chung → "huỷ" (0R). Chờ quá 3 ngày → "hết hạn".
  - Sau khi vào: 50% chốt TP1, 50% chốt TP2; chạm STL thì thoát; nến chạm cả STL lẫn TP tính STL; quá 40 nến thì đóng theo giá.
    Phí 0.1%. R tính trên khoảng cách giá vào thực → STL.
  Lưu ý: alert TradingView chạy trên giá MEXC, sổ chấm bằng nến Binance → có thể lệch vài nến ở mốc sát.
"""
import argparse, json, sys
from datetime import datetime, timezone

import core

JF = core.HERE / "journal.json"
FINAL = ("TP2", "SL", "TP1 rồi SL", "hết 40 nến", "huỷ", "huỷ (BTC)", "không đuổi", "hết hạn", "thay kèo mới")
NOT_ENTERED = ("huỷ", "huỷ (BTC)", "không đuổi", "hết hạn", "thay kèo mới")
FEE, HOLD, WAIT_BARS = 0.001, 40, 18


def load():
    try:
        return json.load(open(JF, encoding="utf-8"))
    except Exception:
        return []


def save(J):
    json.dump(J, open(JF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def add(path):
    P = json.load(open(path, encoding="utf-8")); J = load(); ids = {x["id"] for x in J}
    created = P.get("created") or int(datetime.now(timezone.utc).timestamp())
    n = 0
    for p in P["picks"]:
        side = p["side"].lower(); pid = f"{P['date']}_{p['coin']}_{side}"
        if pid in ids:
            continue
        bc = (P.get("btc_cancel") or {})
        J.append(dict(id=pid, date=P["date"], created=created, coin=p["coin"], side=side, setup=p.get("setup", "?"), level=p["level"],
                      confirm=int(p.get("confirm", 2 if side == "short" else 1)), stop=p["stop"], tp1=p["tp1"], tp2=p["tp2"],
                      no_chase=p.get("no_chase"), cancel=p.get("cancel"), size_r=p.get("size_r"), entry_now=p.get("entry_now"),
                      btc_cancel=bc.get("long_below") if side == "long" else bc.get("short_above"), status="chờ", r=None))
        n += 1
    save(J); print(f"Thêm {n} kèo từ {path} (sổ có {len(J)} kèo)")


def score_one(e, btc, until=None):
    """until: thời điểm có kèo mới cùng coin (kèo chưa vào thì bị thay)."""
    K = core.kl(e["coin"] + "USDT", "4h", 300)[:-1]
    long = e["side"] == "long"; beyond = (lambda c, lv: c > lv) if long else (lambda c, lv: c < lv)
    bclose = {x[0]: x[4] for x in btc}
    e.update(status="chờ", r=None, entry=None, entry_time=None, note="")
    first = next((i for i, x in enumerate(K) if x[0] + 14400 > e["created"]), len(K))    # nến đầu tiên đóng sau lúc tạo kèo
    run = 0
    for x in K[max(0, first - 6):first]:
        run = run + 1 if beyond(x[4], e["level"]) else 0
    ie = None; ent = None
    if e.get("entry_now"):
        ie, ent = first - 1, e["entry_now"]
    else:
        for i in range(first, len(K)):
            x = K[i]
            if until and x[0] + 14400 > until:
                e.update(status="thay kèo mới", r=0.0, note="có kèo mới cùng coin, alert cũ đã xoá"); return e
            if e.get("cancel") is not None and beyond(e["cancel"], x[4]):       # đóng qua mức huỷ (ngược chiều kèo)
                e.update(status="huỷ", r=0.0, note=f"4H đóng {core.num(x[4])} qua mức huỷ {core.num(e['cancel'])}"); return e
            b = bclose.get(x[0])
            if e.get("btc_cancel") and b is not None and (b < e["btc_cancel"] if long else b > e["btc_cancel"]):
                e.update(status="huỷ (BTC)", r=0.0, note=f"BTC 4H đóng {core.num(b)} qua {core.num(e['btc_cancel'])}"); return e
            run = run + 1 if beyond(x[4], e["level"]) else 0
            if run == e["confirm"]:
                if e.get("no_chase") is not None and beyond(x[4], e["no_chase"]):
                    e.update(status="không đuổi", r=0.0, note=f"✅ lúc giá {core.num(x[4])} đã qua mức không đuổi {core.num(e['no_chase'])}"); return e
                ie, ent = i, x[4]; break
            if i - first >= WAIT_BARS:
                e.update(status="hết hạn", r=0.0, note="3 ngày không có ✅"); return e
    if ie is None:
        return e
    k = K
    R = abs(ent - e["stop"]); sg = 1 if long else -1
    e.update(entry=ent, entry_time=e["created"] if e.get("entry_now") else k[ie][0] + 14400)
    if R <= 0 or (ent <= e["stop"] if long else ent >= e["stop"]):
        e.update(status="huỷ", r=0.0, note="giá vào đã qua STL"); return e
    fee = FEE * ent / R; got1 = False; r1 = sg * (e["tp1"] - ent) / R; r2 = sg * (e["tp2"] - ent) / R
    rest = k[ie + 1:]
    for j, x in enumerate(rest[:HOLD]):
        if (x[3] <= e["stop"]) if long else (x[2] >= e["stop"]):
            e.update(status="TP1 rồi SL" if got1 else "SL", r=round(0.5 * (r1 if got1 else -1) - 0.5 - fee, 2)); return e
        if not got1 and ((x[2] >= e["tp1"]) if long else (x[3] <= e["tp1"])):
            got1 = True
        if got1 and ((x[2] >= e["tp2"]) if long else (x[3] <= e["tp2"])):
            e.update(status="TP2", r=round(0.5 * r1 + 0.5 * r2 - fee, 2)); return e
    last = (rest[min(len(rest), HOLD) - 1][4] if rest else ent); cur = sg * (last - ent) / R
    rr = round(0.5 * (r1 if got1 else cur) + 0.5 * cur - fee, 2)
    if len(rest) >= HOLD:
        e.update(status="hết 40 nến", r=rr)
    else:
        e.update(status="đang mở (đã TP1)" if got1 else "đang mở", r=rr, note=f"giá {core.num(last)}")
    return e


def score():
    J = load(); btc = core.kl("BTCUSDT", "4h", 300)[:-1]
    for e in J:
        if e["status"] not in FINAL:
            try:
                nxt = [x["created"] for x in J if x["coin"] == e["coin"] and x["created"] > e["created"]]
                score_one(e, btc, min(nxt) if nxt else None)
            except Exception as ex:
                e["note"] = f"lỗi chấm: {ex}"
    save(J); return J


def table(J, days=4):
    now = datetime.now(timezone.utc).timestamp()
    f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%d/%m %Hh") if t else "—"
    print("| Kèo | Mốc ✅ | Vào (UTC) | STL | TP1 / TP2 | Trạng thái | R | Ghi chú |\n|---|---|---|---|---|---|---|---|")
    for e in J:
        if now - e["created"] > days * 86400 and e["status"] in FINAL:
            continue
        ent = f"{core.num(e['entry'])} ({f(e['entry_time'])})" if e.get("entry") else "chưa vào"
        r = "—" if e["r"] is None else f"{e['r']:+.2f}R"
        print(f"| {e['side'].upper()} {e['coin']} {e['date'][8:]}/{e['date'][5:7]} [{e['setup']}] | {core.num(e['level'])} ×{e['confirm']} nến | {ent} | "
              f"{core.num(e['stop'])} | {core.num(e['tp1'])} / {core.num(e['tp2'])} | {e['status']} | {r} | {e.get('note', '')} |")


def stats(J):
    now = datetime.now(timezone.utc).timestamp()
    print("| Giai đoạn | Setup | Kèo báo | Đã vào | Thắng | Tổng R | TB R/lệnh | Không vào (huỷ/hết hạn/không đuổi/thay) |\n|---|---|---|---|---|---|---|---|")
    for days in (7, 30):
        sub = [e for e in J if now - e["created"] <= days * 86400]
        for setup in sorted({e["setup"] for e in sub}) + ["TẤT CẢ"]:
            s = [e for e in sub if setup == "TẤT CẢ" or e["setup"] == setup]
            ent = [e for e in s if e.get("entry") and e["r"] is not None]
            win = sum(1 for e in ent if e["r"] > 0); tot = sum(e["r"] for e in ent)
            skip = sum(1 for e in s if e["status"] in NOT_ENTERED)
            print(f"| {days} ngày | {setup} | {len(s)} | {len(ent)} | {win}/{len(ent)} | {tot:+.2f}R | {(tot / len(ent)) if ent else 0:+.2f}R | {skip} |")
    print("\n(R của lệnh đang mở tính theo giá hiện tại. Mẫu nhỏ thì chưa kết luận được gì.)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["add", "score", "stats"]); ap.add_argument("--file"); ap.add_argument("--days", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "add":
        p = a.file or core.newest("picks.json")
        if not p:
            sys.exit("Không thấy picks.json")
        add(p)
    elif a.cmd == "score":
        table(score(), a.days)
    else:
        stats(score())
