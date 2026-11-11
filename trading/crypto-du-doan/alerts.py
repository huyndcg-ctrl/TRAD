"""ĐẶT BỘ ALERT TradingView từ picks.json (thay cho việc viết alerts_NN.py mỗi ngày).

  python alerts.py [--file YYYY-MM-DD/picks.json]            chạy thử: in nội dung từng alert, KHÔNG tạo gì
  python alerts.py --apply                                    dọn alert cũ của Claude (cleanup_alerts.py) rồi tạo alert, kiểm tra active
  python alerts.py --list                                     liệt kê alert của Claude đang có (chỉ đọc)

Mỗi kèo 3 alert, tag cuối "[COIN mốc · kịch bản DD/MM]":
  ⏳ chạm mốc (1 phút, bắn 1 lần)               — chỉ là thông tin, ghi rõ CHƯA VÀO / CHƯA BUY
  ✅ lệnh vào: long confirm=1 → nến 4H đóng qua mốc (alert giá, on_bar_close)
              confirm≥2      → indicator Pine "Claude 2-close alert" (bắn đúng nến thứ N)
  ❌ bỏ kèo: nến 4H đóng qua `cancel`
Thêm ❌ BỎ TẤT CẢ LONG / SHORT theo mốc BTC trong `btc_cancel`.
Kèo có `entry_now` (đã ✅ ngay trong báo cáo) thì không tạo ⏳/✅, chỉ tạo ❌.

picks.json:
{"date": "2026-11-11",
 "btc_cancel": {"long_below": 72690, "long_why": "...", "short_above": 74500, "short_why": "..."},
 "picks": [{"coin": "HYPE", "side": "short", "setup": "BD_S_alert", "level": 70.35, "confirm": 2, "stop": 73.0, "tp1": 67.0, "tp2": 63.9,
            "no_chase": 69.0, "cancel": 73.0, "size_r": 0.3, "why": "...", "cancel_why": "..."}]}
Cần TradingView Desktop mở cổng 9222 (không bấm "Kết nối" nếu thấy hộp "Phiên bị ngắt kết nối"). Không đổi symbol chart.
"""
import argparse, asyncio, json, subprocess, sys

import core

# indicator Pine "Claude 2-close alert" (nguồn: claude_2close.pine). Id riêng của tài khoản TradingView → để trong tv_local.json (không đưa lên git)
try:
    _tv = json.load(open(core.HERE / "tv_local.json", encoding="utf-8")); PID, PVER = _tv["pine_id"], _tv.get("pine_version", "1.0")
except Exception:
    PID = PVER = None
BINANCE_SYMS = {"1000PEPE", "PUMP"}                                # coin mà MEXC đặt tên khác → dùng chart Binance
JS = """(async()=>{const r=await fetch('https://pricealerts.tradingview.com/%s',{method:'POST',credentials:'include',headers:{'Content-Type':'text/plain;charset=UTF-8'},body:JSON.stringify(%s)});return await r.text()})()"""
LIST = "(async()=>{const r=await fetch('https://pricealerts.tradingview.com/list_alerts',{credentials:'include'});return await r.text()})()"
N = core.num


def sym(coin):
    ex = "BINANCE" if coin in BINANCE_SYMS else "MEXC"
    return "=" + json.dumps({"symbol": f"{ex}:{coin}USDT.P", "adjustment": "splits", "session": "regular", "currency-id": "XTVCUSDT"}, separators=(",", ":"))


def _base(coin, res, msg, cond):
    return {"payload": {"symbol": sym(coin), "resolution": res, "message": msg, "popup": True, "email": True, "sms_over_email": True, "mobile_push": True,
                        "active": True, "ignore_warnings": True, "auto_deactivate": True, "conditions": [cond]}}


def price(coin, typ, res, freq, px, msg):
    return _base(coin, res, msg, {"type": typ, "frequency": freq, "series": [{"type": "barset"}, {"type": "value", "value": px}], "cross_interval": True, "resolution": res})


def pine(coin, lvl, side, n, msg):
    if not PID:
        sys.exit('Thiếu tv_local.json {"pine_id": "USER;...", "pine_version": "1.0"} — id của indicator "Claude 2-close alert" trên TradingView.')
    return _base(coin, "240", msg, {"type": "pine_alert", "frequency": "on_bar_close", "cross_interval": False, "resolution": "240",
                                    "series": [{"type": "study", "study": "Script@tv-scripting-101", "pine_id": PID, "pine_version": PVER,
                                                "inputs": {"__fast_calc": False, "__profile": False, "in_0": lvl, "in_1": side, "in_2": n, "in_3": msg,
                                                           "pineFeatures": '{"indicator":1,"plot":1,"alert":1}'}, "offsets_by_plot": {"plot_0": 0}}]})


def build(P):
    """→ [(coin, giá, loại ⏳/✅/❌, body)]"""
    dm = f"{P['date'][8:10]}/{P['date'][5:7]}"; T = f"· kịch bản {dm}]"; A = []
    bc = P.get("btc_cancel") or {}
    longs = [p["coin"] for p in P["picks"] if p["side"].lower() == "long"]; shorts = [p["coin"] for p in P["picks"] if p["side"].lower() == "short"]
    for p in P["picks"]:
        c = p["coin"]; long = p["side"].lower() == "long"; S = "LONG" if long else "SHORT"
        lvl, n = p["level"], int(p.get("confirm", 1 if long else 2))
        up, dn = ("cross_up", "cross_down") if long else ("cross_down", "cross_up")
        hon = "trên" if long else "dưới"; nguoc = "dưới" if long else "trên"
        size = f" Kèo này {p['size_r']}R." if p.get("size_r") else ""
        tag = lambda px: f" [{c} {px} {T}"
        allx = f"❌ BỎ TẤT CẢ {'LONG' if long else 'KÈO SHORT'} {dm}"
        if not p.get("entry_now"):
            cho = "nến 4H ĐÓNG" if n == 1 else f"{n} nến 4H LIÊN TIẾP đóng"
            A.append((c, lvl, "⏳", price(c, up, "1", "on_first_fire", lvl,
                      f"⏳ {c} CHƯA {'BUY' if long else 'VÀO SHORT'}. Giá chạm mốc {N(lvl)}. Chỉ vào khi {cho} {hon} {N(lvl)}. Chờ alert ✅."
                      + (" Lệnh BUY hiện tại: không có." if long else "") + tag(lvl))))
            nc = f" KHÔNG đuổi nếu giá lúc này đã {hon} {N(p['no_chase'])}." if p.get("no_chase") is not None else ""
            msg = (f"✅ VÀO {S} {c} NGAY tại giá hiện tại (quanh {N(lvl)}) | STL {N(p['stop'])} | TP1 {N(p['tp1'])} – TP2 {N(p['tp2'])}. "
                   f"Vì sao: {'nến 4H vừa đóng' if n == 1 else f'{n} nến 4H liên tiếp vừa đóng'} {hon} {N(lvl)}, {p.get('why', '')}."
                   f"{' Vào NGAY, không chờ retest.' if long else ''}{size}{nc} Nếu trước đó đã nhận ❌ BỎ KÈO {S} {c} hoặc {allx} thì KHÔNG vào." + tag(lvl))
            A.append((c, lvl, "✅", price(c, up, "240", "on_bar_close", lvl, msg) if n == 1 else pine(c, lvl, "long" if long else "short", n, msg)))
        if p.get("cancel") is not None:
            cx = p["cancel"]
            A.append((c, cx, "❌", price(c, dn, "240", "on_bar_close", cx,
                      f"❌ BỎ KÈO {S} {c}: chưa vào thì thôi, đang giữ thì đóng. Vì sao: nến 4H đóng {nguoc} {N(cx)} → {p.get('cancel_why', 'kịch bản hỏng')}." + tag(cx))))
    if longs and bc.get("long_below"):
        x = bc["long_below"]
        A.append(("BTC", x, "❌", price("BTC", "cross_down", "240", "on_bar_close", x,
                  f"❌ BỎ TẤT CẢ LONG {dm} ({', '.join(longs)}): chưa buy thì thôi, đang giữ thì đóng. Vì sao: BTC nến 4H đóng dưới {N(x)} → {bc.get('long_why', 'thị trường giảm tiếp')}. [BTC {x} {T}")))
    if shorts and bc.get("short_above"):
        x = bc["short_above"]
        A.append(("BTC", x, "❌", price("BTC", "cross_up", "240", "on_bar_close", x,
                  f"❌ BỎ TẤT CẢ KÈO SHORT {dm} ({', '.join(shorts)}): chưa vào thì thôi; đang giữ thì dời STL về giá vào (hoà vốn). Vì sao: BTC nến 4H đóng trên {N(x)} → {bc.get('short_why', 'thị trường hồi')}. [BTC {x} {T}")))
    return A, T, dm


async def cdp():
    import bambam_confluence as b
    c = await b.CDP().__aenter__()
    if await c.ev("document.body.innerText.includes('Phiên bị ngắt kết nối')"):
        await c.__aexit__(); sys.exit("TradingView: 'Phiên bị ngắt kết nối' — KHÔNG bấm Kết nối; bỏ qua phần alert.")
    return c


async def main(a):
    if a.list:
        c = await cdp()
        L = [x for x in json.loads(await c.ev(LIST))["r"] if "· kịch bản " in x["message"] or "· nhánh giảm " in x["message"]]
        for x in L:
            print(x["alert_id"], "active" if x.get("active") else "ĐÃ BẮN/TẮT", "|", x["message"][:110])
        print(len(L), "alert của Claude"); await c.__aexit__(); return
    path = a.file or core.newest("picks.json")
    if not path:
        sys.exit("Không thấy picks.json")
    P = json.load(open(path, encoding="utf-8")); A, T, dm = build(P)
    print(f"{path} → {len(A)} alert, tag '{T}'")
    for coin, px, kind, body in A:
        cond = body["payload"]["conditions"][0]
        print(f"\n{kind} {coin} @ {N(px)} [{cond['type']}, {cond['resolution']}, {cond['frequency']}]\n   {body['payload']['message']}")
        if len(body["payload"]["message"]) > 1900:
            print("   ⚠️ nội dung quá dài")
    if not a.apply:
        print("\n(Chạy thử — chưa tạo alert nào. Thêm --apply để dọn alert cũ và tạo thật.)"); return
    coins = ",".join(sorted({p["coin"] for p in P["picks"]}))
    r = subprocess.run([sys.executable, str(core.HERE / "cleanup_alerts.py"), "--replace", coins, "--today", dm, "--apply"], capture_output=True, text=True, encoding="utf-8")
    print("\n--- dọn alert cũ ---\n" + (r.stdout or "") + (r.stderr or "")[-400:])
    c = await cdp()
    have = {x["message"] for x in json.loads(await c.ev(LIST))["r"]}
    for coin, px, kind, body in A:
        if body["payload"]["message"] in have:
            print("đã có, bỏ qua:", kind, coin, px); continue
        r = await c.ev(JS % ("create_alert", json.dumps(body, ensure_ascii=False)))
        print("tạo", kind, coin, px, "→", r[:80])
    L = json.loads(await c.ev(LIST))["r"]; mine = [x for x in L if T in x["message"]]
    bad = [x for x in mine if not x.get("active") or x.get("last_error")]
    print(f"\nTổng {len(L)} alert | kịch bản {dm}: {len(mine)} | active {len(mine) - len(bad)}" + (f" | ⚠️ LỖI: {[(x['alert_id'], x.get('last_error')) for x in bad]}" if bad else ""))
    await c.__aexit__()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--file"); ap.add_argument("--apply", action="store_true"); ap.add_argument("--list", action="store_true")
    asyncio.run(main(ap.parse_args()))
