---
name: scan-channel
description: |
  Quét 1 hoặc nhiều coin crypto qua TradingView Desktop để xác định giá đang nằm ở đâu trong "kênh giá" trên khung 1H/4H/1D — dùng cả kênh VWAP Bands (indicator có sẵn trên chart) lẫn kênh hồi quy tuyến tính tự tính từ dữ liệu nến thô — rồi kết luận coin đó buyable ngay, nên chờ pullback về vùng nào, hay đang quá extended nên tránh/chốt lời. Dùng skill này bất cứ khi nào người dùng nói "quét theo kênh", "quét kênh", "scan channel", "coin này có mua được không", "check kênh giá", hoặc đưa tên 1-nhiều coin và hỏi có nên vào lệnh / limit ở đâu / đang extended hay chưa. Coin cần quét luôn lấy từ chính yêu cầu của người dùng ở lượt gọi đó — skill không có danh sách coin mặc định cố định.
---

# Scan Channel — quét vị trí giá trong kênh qua TradingView

Skill này đóng gói lại quy trình đã dùng thủ công nhiều lần: kết nối TradingView Desktop, đọc bộ chỉ báo trên chart (kênh VWAP, mây Ichimoku, vùng thanh khoản, EMA, swing high/low), cộng thêm một kênh hồi quy tuyến tính tự tính (vì TradingView không xuất được số liệu của "Linear Regression Channel" qua Data Window — nó chỉ vẽ đường, không có `plot()` output), rồi tổng hợp thành bảng + kết luận buyable hay không cho từng coin trên 3 khung 1H/4H/1D.

## Thông tin hệ thống

| Mục | Giá trị |
|---|---|
| Đường dẫn TradingView (thử trước) | `C:\Users\dell\TradingView-portable\TradingView.exe` |
| Package AppX (fallback, đã xác nhận hoạt động ổn định) | Tên gói khớp `TradingView*`, cài dưới `C:\Program Files\WindowsApps\` |
| Debug port | `9222` |
| Script tính kênh hồi quy | `scripts/regression_channel.py` (thuần Python, không cần numpy) |

## Bước 1 — Kết nối TradingView

Gọi `tv_health_check`. Nếu `cdp_connected: true` → bỏ qua phần dưới, sang Bước 2.

Nếu chết kết nối, TradingView Desktop trên máy này thường tự bung nhiều tiến trình MSIX riêng biệt sau lần chạy trước — không tắt hết được bằng `taskkill` thường (báo "Access is denied" vì đây là tiến trình AppX container). Dùng đúng trình tự sau (đã kiểm chứng qua nhiều phiên):

```powershell
Get-Process -Name TradingView -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 3
$pkg = Get-AppxPackage -Name '*TradingView*' | Select-Object -First 1
$exe = Join-Path $pkg.InstallLocation 'TradingView.exe'
$appId = (Get-AppxPackageManifest $pkg).Package.Applications.Application.Id
Invoke-CommandInDesktopPackage -PackageFamilyName $pkg.PackageFamilyName -AppId $appId -Command $exe -Args '--remote-debugging-port=9222'
Start-Sleep 8
try { (Invoke-WebRequest -Uri http://127.0.0.1:9222/json/version -UseBasicParsing -TimeoutSec 5).Content } catch { "no response" }
```

Nếu port 9222 phản hồi JSON hợp lệ → gọi lại `tv_health_check` để xác nhận `cdp_connected: true`. Nếu vẫn thất bại sau 2 lần thử, báo cho người dùng thay vì lặp vô hạn.

## Bước 2 — Xác định danh sách coin cần quét

Lấy trực tiếp từ câu người dùng vừa gõ (ví dụ "quét kênh BTC ETH SOL" → `["BTC","ETH","SOL"]`). Không tự thêm coin nào ngoài danh sách này, không dùng danh sách mặc định.

Map mỗi coin sang symbol perpetual trên Binance: `BINANCE:{COIN}USDT.P`. Nếu lúc set symbol mà `chart_ready` không lên hoặc quote trả về sai coin (ví dụ giá trị bất thường không khớp coin đang hỏi), thử fallback `OKX:{COIN}USDT.P` trước khi báo lỗi coin đó không quét được.

## Bước 3 — Với mỗi coin, mỗi khung thời gian (1D → 4H → 1H)

1. `chart_set_symbol` rồi `chart_set_timeframe` (`D`, `240`, `60`). **Cả hai tool này có thể báo `success`/`chart_ready: true` dù chart THỰC TẾ chưa đổi** (đã gặp nhiều lần: set symbol xong đọc data vẫn ra coin cũ do TradingView Desktop bị điều khiển song song, hoặc set timeframe xong `resolution` vẫn giữ khung cũ). Vì vậy **luôn gọi `chart_get_state` ngay sau đó để xác nhận `symbol` đúng coin và `resolution` đúng khung** trước khi đọc bất kỳ data nào — nếu sai, set lại và kiểm tra lại, không giả định lệnh vừa gọi đã có hiệu lực.
2. `quote_get` — giá hiện tại.
3. `data_get_ohlcv(count=24-30, summary=true)` — % thay đổi, range, volume để có ngữ cảnh.
4. `data_get_ohlcv(count=50, summary=false)` — lấy 50 nến thô, trích mảng `close` (nến mới nhất phải ở **cuối** mảng, đúng thứ tự trả về từ tool).
5. `data_get_study_values` — đọc toàn bộ chỉ báo đang có trên chart của người dùng (thường đã có sẵn: `Liquidation Levels [LuxAlgo]` → field `Bubbles`, `Ichimoku Theories [LuxAlgo]` → `KinjuSen`/`SenkouSpanA`/`SenkouSpanB`, `BAMBAM with VWAP Bands [Optimized]` → đây chính là **kênh VWAP**, `Moving Average Exponential` → `EMA`, `SMC: Sweep + CHoCH + OB + FVG [Entry Signal]` → `Swing High`/`Swing Low`).
   - **Không tự ý thêm indicator mới** trừ khi một trong các chỉ báo trên hoàn toàn vắng mặt trong kết quả — chart của người dùng đã có sẵn bộ này từ lâu, thêm lại dễ tạo bản trùng (đã từng thấy `Moving Average Exponential` bị nhân đôi trong phiên trước). Nếu thật sự thiếu, kiểm tra `chart_get_state` để chắc chưa có tên đó rồi mới `chart_manage_indicator(action="add", ...)`.
   - Nếu 1 field bị trùng tên (2 lần `Moving Average Exponential` chẳng hạn), lấy giá trị của lần xuất hiện đầu tiên.

## Bước 4 — Tính kênh hồi quy tuyến tính

Pipe mảng `close` (50 giá trị, cũ→mới) lấy từ bước 3.4 vào script:

```bash
echo "[c1,c2,...,c50]" | python "$HOME/.claude/skills/scan-channel/scripts/regression_channel.py"
```

(Trên Windows, dùng `python` — không phải `python3`.) Script trả JSON gồm `basis_now`, `upper_2sd`, `lower_2sd`, `pct_position_in_channel` (0% = đáy kênh, 100% = đỉnh kênh, có thể âm hoặc >100 nếu giá đã phá kênh), và `note` diễn giải sẵn (quanh đỉnh/đáy kênh, đã phá kênh, hay ở giữa).

## Bước 5 — Phân loại vị trí trong từng kênh

**Kênh VWAP** (từ `BAMBAM with VWAP Bands [Optimized]`): so giá hiện tại với `Top Upper (inner)` / `Top Outer (2SD)` (kháng cự) và `Bottom Upper (inner)` / `Bottom Outer (2SD)` (hỗ trợ, chỉ áp dụng cho khung có giá trị hợp lý — với coin đang uptrend dài hạn, dải Bottom có thể ở rất xa, không có ý nghĩa thực tế, lúc đó chỉ dùng dải Top).
- Giá ≥ `Top Outer (2SD)` → **"vượt dải trên — extended nặng"**
- Giá trong khoảng `Top Upper (inner)` đến `Top Outer (2SD)` → **"áp sát biên trên — extended"**
- Giá dưới `Top Upper (inner)` và trên vùng hỗ trợ tương ứng → **"trong kênh — trung tính"**
- Giá chạm/dưới vùng hỗ trợ (Liquidation Bubble hoặc Bottom band) → **"chạm biên dưới — vùng cân nhắc mua"**

**Kênh hồi quy** (từ script): dùng thẳng field `note` — `pct_position_in_channel > 85` = quá mua trong kênh, `< 15` = quá bán trong kênh, âm hoặc >100 = đã phá kênh hẳn (tín hiệu breakout thật hoặc parabolic cần cẩn trọng hơn nữa).

**Đối chiếu thêm:** Liquidation Bubble gần nhất (nam châm thanh khoản), mây Ichimoku (Kijun/SpanA/SpanB — giá trên mây = trend chính còn nguyên), Swing High/Low gần nhất (mốc breakout/breakdown).

## Bước 6 — Output

Với mỗi coin, trình bày đúng format sau (giữ nguyên phong cách đã dùng — bảng markdown, không thêm phần thừa):

```markdown
## {COIN} — ${giá hiện tại}, {% thay đổi 24h theo khung 4H}

| | 1D | 4H | 1H |
|---|---|---|---|
| Giá | ... | ... | ... |
| Kênh VWAP | {trạng thái} (${mức chạm}) | ... | ... |
| Kênh hồi quy (% vị trí) | {X}% ({note}) | ... | ... |
| Ichimoku Kijun/Cloud | ... | ... | ... |
| Liquidation Bubble | ... | ... | ... |
| Swing High/Low | ... | ... | ... |

**Verdict:** {Buyable ngay / Chờ pullback về $X (nêu rõ vùng hợp lưu — nơi cả kênh VWAP, kênh hồi quy, và mây/bubble trùng nhau) / Overextended — không mua đuổi}

**Limit gợi ý:** mua thêm ${vùng hợp lưu dưới} · chốt lời/giảm risk ${vùng hợp lưu trên}
```

Nếu quét nhiều coin, xếp coin theo mức độ "buyable" giảm dần (ít extended nhất lên trước) giống cách đã làm khi so sánh nhiều coin trong 1 lần, kèm 1 bảng tóm tắt ở đầu.

## Lưu ý quan trọng

- Luôn ưu tiên **vùng hợp lưu** (nơi ≥2 trong số: kênh VWAP, kênh hồi quy, mây Ichimoku, Liquidation Bubble, Swing High/Low trùng nhau trong khoảng giá gần nhau) làm điểm entry/stop cụ thể — không dùng 1 chỉ báo đơn lẻ để chốt kết luận.
- Kênh hồi quy tính trên 50 nến gần nhất của khung đang xét — với coin mới breakout mạnh (biến động parabol), `pct_position_in_channel` có thể vọt rất cao (>150%) vì kênh chưa kịp giãn theo giá; đó chính là tín hiệu "cực kỳ extended", không phải lỗi tính toán.
- Nếu người dùng đang hold coin đó (biết được từ ngữ cảnh hội thoại), luôn kèm gợi ý quản trị vị thế (chốt bớt / giữ / mốc theo dõi) chứ không chỉ trả lời buyable hay không.
- Đây là phân tích kỹ thuật, không phải khuyến nghị đầu tư cá nhân hóa — giữ đúng tinh thần đó khi kết luận.
