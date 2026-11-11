# crypto-du-doan

Phân tích, quét kèo, vẽ dự đoán đường giá, đặt alert và chuẩn bị lệnh crypto (làm cùng Claude).

## Quy trình hằng ngày (routine 8h tự chạy, cũng chạy tay được)

```
python scan_all.py            # 1 lệnh: chế độ thị trường + BTC/ETH + mọi loại kèo 4H, kèm kỳ vọng R theo backtest
python journal.py score       # tự chấm các kèo đã báo bằng nến thật
python journal.py stats       # thành tích 7 / 30 ngày theo loại setup
# ghi kèo đã chọn vào YYYY-MM-DD/picks.json (mẫu trong docstring alerts.py)
python journal.py add         # đưa kèo hôm nay vào sổ
python alerts.py              # xem thử nội dung alert (không tạo gì)
python alerts.py --apply      # dọn alert cũ của Claude + tạo ⏳/✅/❌ trên TradingView
```

Hằng tháng: `python backtest.py` (tạo lại `expectancy.json`). Sau khi sửa code: `python qa_check.py`.

## Cấu trúc
- `YYYY-MM-DD/` — kết quả từng ngày: `scan.json`, `picks.json`, `bao_cao_sang.md`, ảnh dự đoán, `setups.json` (kèo để đặt MEXC)…
- `journal.json` — sổ kèo (mọi kèo đã báo + kết quả tự chấm). `expectancy.json` — kỳ vọng R từng setup theo backtest gần nhất.
- `_cache/` — cache nến 4 phút (xoá được). `_cu/` — script cũ và bản sao lưu trước nâng cấp 11/11/2026.

| File | Việc |
|---|---|
| `core.py` | **Lõi chung**: dữ liệu Binance (cache), EMA/RSI/ATR/Ichimoku/pivot, bộ lọc chất lượng coin (`quality`, `BLACKLIST`, tự nhận token cổ phiếu/ETF và coin mới theo Binance), chế độ thị trường |
| `scan_all.py` | Quét một lệnh: breakout long, breakdown short (1/2, 2/2), long hồi, short hồi, sắp phá mốc. Định nghĩa trùng backtest |
| `backtest.py` | Backtest 8 biến thể setup 4H, theo bối cảnh BTC/độ rộng, có chia đôi giai đoạn (ngoài mẫu) → `expectancy.json` |
| `journal.py` | Sổ kèo: `add` / `score` / `stats` |
| `alerts.py` | Tạo bộ alert TradingView từ `picks.json` (✅ 2 nến dùng indicator Pine `claude_2close.pine`) |
| `cleanup_alerts.py` | Dọn alert của Claude: kèo đã ❌, cũ > 3 ngày, trùng coin kèo mới |
| `qa_check.py` | Kiểm tra tự động: chỉ báo, không nhìn trước, mô phỏng lệnh, bộ lọc, alert, sổ kèo |
| `bambam_confluence.py` | Đọc Sơn Dubai OB/FVG, Swing VP, BAMBAM VWAP trên TradingView + khung lớn → chấm điểm, vùng vào/STL/TP (đổi coin trên chart rồi trả lại) |
| `breakout_scan.py` | Quét breakout có volume 1H/4H + nhóm sắp breakout (4H: long vào ngay, short chờ nến thứ 2) |
| `setup_scan_4h.py`, `range_scan.py`, `market_scan.py`, `watchlist_scan.py` | Các bản quét cũ, vẫn chạy được, dùng bộ lọc TradFi của `core` |
| `pattern_scan.py`, `deep_check.py` | Tìm form trước khi tăng giống INJ/PEPE/XMR; kiểm tra sâu dòng tiền + phái sinh |
| `dat_lenh_mexc.bat` + `mexc_entry.py` | **Bạn tự chạy**: đặt lệnh MEXC theo `setups.json` mới nhất (`--plan` xem trước; xác nhận Y từng lệnh) |
| `dat_sl_mexc.bat` + `mexc_sl.py` | **Bạn tự chạy**: gắn SL/TP theo `sl_plan.json` |
| `huy_lenh_mexc.bat` + `mexc_cancel.py` | **Bạn tự chạy**: huỷ lệnh chờ theo `cancel_plan.json` |
| `mexc_positions.py` | Đọc vị thế MEXC (chỉ đọc) |

## Quy tắc đang áp dụng
- Chỉ chữ "✅ VÀO LONG/SHORT …" mới là lệnh vào. ⏳ chỉ là thông tin. ❌ bắn thì alert ⏳/✅ của kèo đó bị xoá tự động.
- Breakout long: vào ngay sau nến 4H đóng trên mốc. Breakdown short: 2 nến 4H liên tiếp đóng dưới mốc.
- Chỉ đề xuất setup có kỳ vọng > 0 trong bối cảnh BTC 4H hiện tại; setup "không ổn định" (không dương ở cả hai nửa giai đoạn) tối đa 0.3R.
- Claude không bao giờ tự đặt/huỷ lệnh hay đụng tới API key; mọi thao tác MEXC do bạn chạy file `.bat`.

## Chạy trong PowerShell
```
cd C:\Users\dell\Desktop\trad\crypto-du-doan
python scan_all.py
.\dat_lenh_mexc.bat --plan
```
