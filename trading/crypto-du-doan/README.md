# crypto-du-doan

Phân tích, vẽ dự đoán đường giá và đặt lệnh crypto (làm cùng Claude).

## Cấu trúc
- `YYYY-MM-DD/` — kết quả của từng ngày: ảnh dự đoán (.png), spec (.json), lệnh vẽ TradingView (`_tv.js`), kết quả quét, `setups.json` (kèo để đặt MEXC).
- Script dùng chung (ở thư mục này):

| File | Việc |
|---|---|
| `dat_lenh_mexc.bat` | Bấm đúp để đặt lệnh MEXC theo `setups.json` của ngày mới nhất (xác nhận YES từng lệnh) |
| `mexc_entry.py` | Script đặt lệnh (`--plan` xem trước, `--dry-run` xem request, `--file` chọn file kèo khác) |
| `dat_sl_mexc.bat` + `mexc_sl.py` | Bấm đúp để gắn SL (và TP) cho vị thế đang mở theo `YYYY-MM-DD/sl_plan.json` (xác nhận Y từng vị thế) |
| `bambam_confluence.py` | Kết hợp indicator layout BAMBAM (Sơn Dubai OB/FVG, Swing VP, BAMBAM VWAP) + EMA/Ichimoku khung lớn → chấm điểm A/B/C, vùng vào/STL/TP. Cần TradingView mở cổng 9222; chart tự đổi coin rồi trả lại |
| `breakout_scan.py` | Quét breakout có volume khung 1H/4H (+ nhóm sắp breakout) |
| `watchlist_scan.py` | Phân tích các coin trong watchlist TradingView: trend 4H/1D + volume chi tiết |
| `setup_scan_4h.py` | Quét kèo khung 4H (pullback theo trend 1D, breakout 4H) |
| `mexc_positions.py` | Đọc vị thế MEXC (chỉ đọc, cần API key quyền đọc trong `mexc_config.json`) |
| `setup_scan.py` | Quét kèo long/short có xác nhận 1H + sentiment BTC 1H |
| `range_scan.py` | Quét coin đi ngang, gợi ý long đáy / short đỉnh range |
| `market_scan.py` | Tổng quan thị trường top coin |

## Chạy trong PowerShell
```
cd C:\Users\dell\Desktop\trad\crypto-du-doan
.\dat_lenh_mexc.bat --plan
.\dat_lenh_mexc.bat
python setup_scan.py
```
