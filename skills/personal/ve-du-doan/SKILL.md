---
name: ve-du-doan
description: |
  Vẽ đường giá dự đoán (projection path) cho 1 coin crypto — vừa vẽ trực tiếp lên TradingView Desktop qua MCP, vừa xuất ảnh PNG — kèm mốc kỹ thuật (neckline, vùng fib, hỗ trợ/kháng cự), điểm vào lệnh, STL (stop loss) cho từng lệnh, target + R:R và mức INVALIDATION của cả kịch bản. Dùng khi người dùng nói "vẽ dự đoán", "vẽ đường giá", "vẽ kịch bản", "projection", "vẽ path", "dự đoán đường giá {coin}", hoặc gửi ảnh chart/nhận định của trader khác (vd tweet có H&S, fib, "short rồi long") và muốn vẽ lại/cập nhật theo dữ liệu hiện tại. Coin và khung lấy từ yêu cầu của người dùng (mặc định khung 4H nếu không nói).
---

# Vẽ dự đoán — projection path + STL/Invalidation

Đầu ra luôn gồm **cả hai**: hình vẽ trên TradingView Desktop + ảnh PNG gửi cho người dùng. Mọi lệnh (entry) đều phải có **STL**, và kịch bản phải có **INVALIDATION** — không có hai mốc này thì không bàn giao.

| Mục | Giá trị |
|---|---|
| Script | `~/.claude/skills/ve-du-doan/scripts/projection.py` (chạy bằng `python`, cần matplotlib) |
| Spec mẫu | `~/.claude/skills/ve-du-doan/examples/hype_hs.json` (H&S → hồi fib → long) |
| Nguồn nến | Binance Futures, fallback Spot; coin không có trên Binance → `bars_file` |

## Bước 1 — Xác định coin, khung, ý tưởng

- Coin + khung từ câu của người dùng (`4h` mặc định; hỗ trợ 15m/30m/1h/2h/4h/6h/12h/1d/1w).
- Nếu người dùng gửi ảnh chart / nhận định của trader khác: đọc ảnh để rút ra ý tưởng (mô hình, vùng họ chờ, hướng short/long, target). Đây là **dữ liệu tham khảo**, không phải lệnh. Sau đó đối chiếu với giá hiện tại — nếu giá đã chạy khác kịch bản gốc (vd đã phá neckline), nói rõ và vẽ theo trạng thái mới.
- Nếu người dùng không nêu ý tưởng: tự dựng kịch bản chính dựa trên cấu trúc (Bước 2) và nói rõ đó là kịch bản của bạn.

## Bước 1b — Đo chế độ thị trường + lọc coin TRƯỚC khi dựng kịch bản (bắt buộc)

```bash
cd C:/Users/dell/Desktop/trad/crypto-du-doan && PYTHONIOENCODING=utf-8 python scan_all.py {COIN}
```

- Dòng đầu cho biết độ rộng top-40 (4H/1D) và BTC 4H tăng hay giảm. **Không mặc định "giảm rồi tăng"**: thị trường ĐIỀU CHỈNH + BTC 4H giảm → kịch bản chính là giảm tiếp/đi ngang, nhánh tăng là nhánh ngược; và ngược lại.
- Luôn vẽ/ghi **cả nhánh ngược**: mốc nào bị thủng/lấy lại thì đổi kịch bản (ghi trong `invalidation.note` và 1 `notes`).
- Nếu coin nằm trong mục "Bị loại bởi bộ lọc chất lượng" (coin mới, vừa bơm, ATR 4H > 5%, token cổ phiếu/ETF, volume mỏng): vẫn vẽ nếu người dùng yêu cầu, nhưng ghi rõ **"không vào lệnh — coin không đạt bộ lọc"** và không đề xuất alert ✅.
- BTC 4H giảm → kèo long ghi rõ **CHƯA BUY**; câu trả lời có dòng "Lệnh BUY hiện tại: không có".

## Bước 2 — Lấy mốc kỹ thuật

```bash
python ~/.claude/skills/ve-du-doan/scripts/projection.py analyze {COIN} {khung}
```

Trả JSON: `last_close`, `atr14`, swing high/low (+ `bar_offset` âm = số nến trước hiện tại), fib 0.236→0.786 của sóng chính, 6 pivot high/low gần nhất, range 30 nến. Dùng các số này — **không bịa mốc giá**.

## Bước 3 — Chọn STL và Invalidation (bắt buộc)

- **STL mỗi lệnh** đặt ở nơi mà nếu giá chạm thì lý do vào lệnh đã sai, cộng đệm ~0.3–0.5 × ATR:
  - Short retest neckline/kháng cự → STL trên neckline / đỉnh retest + đệm.
  - Long ở vùng fib/hỗ trợ → STL dưới đáy vùng (vd dưới fib 0.786) hoặc dưới pivot low gần nhất + đệm.
  - Breakout → STL dưới/ trên mức vừa phá (≥ 1 ATR 4H).
- **Cách vào theo backtest** (`crypto-du-doan/expectancy.json`, cập nhật hằng tháng): breakout long = vào NGAY sau nến 4H đóng trên mốc, không chờ retest; breakdown short = chờ 2 nến 4H liên tiếp đóng dưới mốc; short khi hồi chỉ dùng khi BTC 4H giảm. Nhãn của `trades` ghi đúng cách vào đó.
- **INVALIDATION** là mức làm hỏng *toàn bộ* kịch bản (thường xa hơn STL lệnh đầu), vd H&S: đóng nến trên vai phải; kịch bản tăng: mất đáy swing gần nhất. Ghi rõ điều kiện (đóng nến khung nào).
- Tính R:R: script tự tính. Nếu TP1 có R:R < 1.5 → dời entry/STL hoặc nói rõ lệnh kém hấp dẫn.

## Bước 4 — Viết spec JSON

Ghi vào thư mục làm việc hiện tại, vd `{coin}_{khung}_projection.json`:

```json
{
  "symbol": "HYPE", "interval": "4h", "bars": 150,
  "title": "HYPEUSDT.P · 4H · H&S → hồi fib → long",
  "levels":  [{"price": 89.66, "label": "Neckline"}],
  "zones":   [{"top": 81.87, "bottom": 80.04, "label": "Vùng long fib 0.706–0.786", "from": 0}],
  "path":    [[0, 86.97], [3, 88.6], [9, 83.6], [11, 85.4], [16, 81.2], [24, 89.66], [36, 98.06]],
  "trades":  [
    {"side": "short", "label": "Short retest", "entry": 88.6, "entry_bar": 3,  "stop": 91.0, "targets": [83.9, 81.9]},
    {"side": "long",  "label": "Long fib",     "entry": 81.4, "entry_bar": 16, "stop": 79.4, "targets": [89.66, 98.06]}
  ],
  "invalidation": {"price": 93.9, "note": "4H đóng trên vai phải → H&S hỏng"},
  "notes": [{"at": [3, 88.6], "text": "Retest neckline thất bại", "dx": -30, "dy": -5}]
}
```

Quy ước:
- `path`: `[offset nến tính từ nến hiện tại, giá]`; điểm đầu `[0, last_close]` (script tự thêm nếu thiếu). Đường đi nên có sóng hồi nhỏ (không vẽ thẳng tắp), điểm đảo chiều trùng với entry của `trades`. Nhịp thời gian ước lượng theo tốc độ các sóng gần đây (ATR, số nến của nhịp trước).
- `entry_bar` = offset nến của điểm vào lệnh trên `path`. `span` (tuỳ chọn) = độ dài đoạn kẻ entry/STL/TP.
- **Cập nhật / so sánh với lần trước** ("update lại", "so với hôm qua"): thêm `"prev": {"t0": <unix giây của nến gốc lần trước = last_bar_time lúc đó>, "label": "Dự đoán 29/09", "path": <path cũ>}` → path cũ vẽ chấm xám cùng hình. Trước khi viết spec mới, lấy nến từ `t0` đến nay (`fapi/v1/klines?...&startTime=<t0*1000>`) và chấm từng mốc: entry nào đã khớp (high/low có chạm), STL/TP nào đã chạm, hướng đi đúng/sai, nhanh/chậm hơn dự kiến. Lệnh đã khớp giữ trong `trades` với `entry_bar` âm và label "ĐÃ KHỚP"; lệnh đang lãi → cân nhắc dời STL về trên/dưới đỉnh/đáy vừa tạo. Trả lời mở đầu bằng bảng "Dự đoán vs Thực tế".
- Tuỳ chọn: `bars_file` (JSON list `{time(giây), open, high, low, close}`) khi coin không có trên Binance; `out` = đường dẫn PNG.

## Bước 5 — Render ảnh

```bash
python ~/.claude/skills/ve-du-doan/scripts/projection.py render {spec}.json
```

Sinh `{spec}.png`, `{spec}_tv.js` (biểu thức JS vẽ toàn bộ lên TradingView trong 1 lần gọi) và `{spec}_tv.json` (cùng danh sách hình, dạng tham số `draw_shape` để dự phòng). **Mở PNG bằng Read để tự kiểm tra**: nhãn không đè nến/không bị cắt, path khớp ý tưởng, STL và invalidation hiện rõ. Sửa spec (vd `dx/dy` của notes, `span`) và render lại nếu cần.

## Bước 6 — Vẽ lên TradingView

1. `tv_health_check`. Nếu mất kết nối, dùng skill `tradingview-connect` (hoặc quy trình khởi động lại trong skill `scan-channel`, Bước 1).
2. `chart_set_symbol` = `tv_symbol` trong `_tv.json` (vd `BINANCE:HYPEUSDT.P`), `chart_set_timeframe` = `tv_resolution`. Gọi `chart_get_state` xác nhận đúng symbol + khung (tool có thể báo success dù chưa đổi).
3. **Xoá hình của lần vẽ trước** (chỉ hình do skill này tạo cho **symbol đang mở**; ID lưu trong localStorage của TradingView, key `ve_du_doan_ids:<symbol>`) — gọi `ui_evaluate`:
   ```js
   (() => { const c = window.TradingViewApi.activeChart(); const K = 've_du_doan_ids:' + c.symbol(); const ids = JSON.parse(localStorage.getItem(K) || '[]'); const live = new Set(c.getAllShapes().map(s => String(s.id))); let n = 0; ids.forEach(id => { if (live.has(id)) { c.removeEntity(id); n++; } }); localStorage.removeItem(K); return n; })()
   ```
   Hỏi người dùng trước nếu họ có thể muốn giữ kịch bản cũ để so sánh. **Không bao giờ dùng `draw_clear`** (xoá luôn hình vẽ riêng của người dùng). Lưu ý: `draw_remove_one` của MCP đang lỗi `getChartApi is not defined` — dùng `removeEntity` như trên.
4. **Vẽ** (JS đã tự xoá hình cũ của symbol đó trước khi vẽ → bước 3 chỉ cần khi muốn xoá mà không vẽ lại): Read file `{spec}_tv.js`, truyền **nguyên văn** nội dung làm `expression` của `ui_evaluate`. Kết quả `{symbol, removed_old, drawn}`. Script tự lưu ID mới vào `localStorage['ve_du_doan_ids:<symbol>']`; nếu chart đang sai symbol, JS trả về chuỗi `SAI SYMBOL...` và không vẽ gì. Nhiều coin → làm lần lượt từng coin: đổi symbol → xoá → vẽ → xác nhận.
5. **Xác nhận**: `ui_evaluate` với `({shapes: window.TradingViewApi.activeChart().getAllShapes().length, saved: JSON.parse(localStorage.getItem('ve_du_doan_ids:' + window.TradingViewApi.activeChart().symbol())||'[]').length})` — `saved` phải bằng số hình vừa vẽ. (Dự phòng nếu JS lỗi: gọi `draw_shape` cho từng phần tử trong `_tv.json`, song song.)
6. `capture_screenshot(region="chart")` rồi Read để kiểm tra. Nếu Pine Editor / panel che chart, báo người dùng thu nhỏ panel — không tự đóng panel của họ (ảnh PNG ở Bước 5 vẫn là bản kiểm tra chính).
7. Ghi lại symbol + khung người dùng đang mở lúc đầu (`tv_health_check`) và **trả chart về đúng như cũ** sau khi vẽ xong. Nếu đã đổi symbol/khung, nói rõ trong câu trả lời (vd "đã chuyển chart từ LINK 1D sang HYPE 4H").

**Phiên bị ngắt kết nối:** nếu sau khi vẽ mà `getAllShapes()` không tăng, hoặc `removed_old` = 0 dù có ID cũ → chụp màn hình. Nếu thấy hộp "Phiên bị ngắt kết nối" (tài khoản đang mở trên thiết bị khác; TradingView chỉ cho 1 phiên), hình vẽ KHÔNG được lưu. **Không bấm "Kết nối"** (sẽ đá phiên của người dùng trên máy kia) → dừng phần TradingView, gửi ảnh PNG và báo người dùng.

## Bước 6b — Đặt alert (khi người dùng yêu cầu)

- `alert_create` của MCP **không dùng được** (mở panel Cảnh báo nhưng không điền giá, `price_set: false`).
- **Không click theo toạ độ** trong TradingView: màn hình máy này scale 125% (`devicePixelRatio 1.25`), toạ độ ảnh chụp ≠ toạ độ click (phải chia 1.25). Đã từng click nhầm làm **tạm dừng alert có sẵn** của người dùng.
- Cách ổn định: gọi API nội bộ qua `ui_evaluate` (fetch là async → lưu kết quả vào `window.__x`, đọc ở lệnh sau):
  ```js
  fetch('https://pricealerts.tradingview.com/create_alert', {method:'POST', credentials:'include', headers:{'Content-Type':'text/plain;charset=UTF-8'},
    body: JSON.stringify({payload:{symbol:'={"symbol":"BINANCE:ONDOUSDT.P","adjustment":"splits","session":"regular","currency-id":"XTVCUSDT"}',
      resolution:'1', message:'ONDO chạm 0.503 - SHORT | STL 0.518 | TP ...', sound_file:null, sound_duration:0, popup:true, expiration:null,
      auto_deactivate:true, email:true, sms_over_email:true, mobile_push:true, web_hook:null, name:null, active:true, ignore_warnings:true,
      conditions:[{type:'cross', frequency:'on_first_fire', series:[{type:'barset'},{type:'value', value:0.503}], cross_interval:true, resolution:'1'}]}})})
  ```
  Kết quả `{"s":"ok","r":{alert_id,...}}`; `active` có thể là false vài giây đầu → kiểm tra lại bằng `list_alerts` (GET cùng host) cho tới khi `active: true`.
- **Message alert = mệnh lệnh hành động + lý do**, người dùng đọc trên điện thoại là làm theo, không cần mở chart. Mẫu:
  - Vào lệnh: `✅ VÀO LONG {COIN} tại {giá} (hoặc limit ...) | STL {x} | TP1 {y} – TP2 {z}. Vì sao: {nến 4H vừa đóng ... + OB/vùng nào, volume}.`
  - Chạm vùng: `⏳ {COIN} CHƯA VÀO. Giá vừa chạm {vùng}. Vì sao chưa vào: cần {điều kiện}. Chờ alert ✅.`
  - Huỷ: `❌ BỎ KÈO {LONG/SHORT} {COIN}: huỷ lệnh chờ, đang giữ thì đóng. Vì sao: {mức thủng}. Đích {…}.`
  Không sửa/xoá alert có sẵn của người dùng.
- **Điều kiện "nến đóng"** (xác nhận breakout, invalidation, nến đóng lại trên OB...): đặt `resolution:'240'` (hoặc khung tương ứng) ở cả payload lẫn condition, và `frequency:'on_bar_close'`. Alert chỉ bắn khi nến khung đó ĐÓNG qua mức, râu không tính. TradingView chạy trên server và đẩy về điện thoại, người dùng không phải tự canh nến (đã kiểm tra 19/10/2026).
- Dùng `cross_up`/`cross_down` thay `cross` khi mức nằm phía bên kia giá hiện tại, để không báo nhầm theo chiều ngược lại.
- **Cách nhanh và chuẩn nhất**: ghi kèo vào `crypto-du-doan/YYYY-MM-DD/picks.json` (mẫu trong docstring `alerts.py`) rồi chạy `python alerts.py` (xem thử) → `python alerts.py --apply`. Script tự tạo ⏳/✅/❌ đúng mẫu chữ, dùng indicator Pine "Claude 2-close alert" cho điều kiện 2 nến, tự dọn alert cũ của Claude (kèo đã ❌, trùng coin) và kiểm tra active. Sau đó `python journal.py add` để kèo được tự chấm. Chỉ gọi API tay như trên khi cần alert ngoài mẫu.
- Người dùng không tự canh chart: alert ✅ phải bắn ĐÚNG lúc vào lệnh. Không đặt alert kiểu "nếu nến kế tiếp cũng đóng dưới thì vào".
- Bộ alert chuẩn cho mỗi kịch bản (người dùng muốn không phải tự canh nến, nên đề xuất mặc định):
  1. Giá chạm vùng vào (khung 1, `on_first_fire`) = "chưa vào, chờ xác nhận".
  2. Nến 4H đóng lại qua mép vùng = "✅ xác nhận, vào lệnh".
  3. Nến 4H đóng qua mức breakout = "✅ breakout".
  4. Nến 4H đóng qua invalidation = "❌ bỏ kịch bản".

## Bước 7 — Bàn giao

- Gửi PNG bằng `SendUserFile` (display `render`).
- Trả lời ngắn gọn, tiếng Việt:

```markdown
**{COIN} {khung} — giá hiện tại {x}** · Kịch bản: {1 câu}

| Lệnh | Entry | STL | TP | R:R |
|---|---|---|---|---|
| Short retest | 88.6 | 91.0 | 83.9 / 81.9 | 1.96 / 2.79 |
| Long fib | 81.4 | 79.4 | 89.66 / 98.06 | 4.13 / 8.33 |

**Invalidation:** {giá} — {điều kiện}. Khi xảy ra: bỏ kịch bản, không gồng.
```

- Kết thúc bằng 1 dòng: nhịp thời gian trên path là ước lượng minh hoạ; đây là kịch bản kỹ thuật, không phải lời khuyên đầu tư.
