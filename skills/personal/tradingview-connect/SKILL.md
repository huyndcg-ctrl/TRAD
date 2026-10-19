---
name: tradingview-connect
description: |
  Kết nối TradingView Desktop qua CDP (Chrome DevTools Protocol) và nạp/cập nhật Pine Script indicator lên chart. Dùng skill này bất cứ khi nào người dùng muốn: kết nối TradingView, nạp code Pine Script mới, cập nhật indicator, deploy indicator, hoặc compile Pine Script lên TradingView Desktop. Trigger khi người dùng nói "connect tradingview", "nạp indicator", "deploy code", "kết nối tradingview", hoặc bất kỳ yêu cầu nào liên quan đến TradingView Desktop và Pine Script.
---

# TradingView Desktop – Kết nối và Deploy Indicator

## Thông tin hệ thống

| Mục | Giá trị |
|-----|---------|
| Đường dẫn TradingView | `C:\Users\dell\TradingView-portable\TradingView.exe` |
| Debug port | `9222` |

## Quy trình thực hiện

### Bước 1 – Kiểm tra kết nối

Gọi `tv_health_check`. Nếu kết quả có `api_available: true` → bỏ qua Bước 2, nhảy thẳng sang Bước 3.

### Bước 2 – Khởi động TradingView (chỉ khi chưa kết nối)

Chạy PowerShell:
```
Start-Process "C:\Users\dell\TradingView-portable\TradingView.exe" -ArgumentList "--remote-debugging-port=9222"
```

Chờ 6 giây:
```
Start-Sleep -Seconds 6
```

Gọi lại `tv_health_check` để xác nhận `api_available: true`.

Nếu vẫn chưa kết nối sau 6s, chờ thêm 4s và thử lại lần nữa.

### Bước 3 – Mở Pine Editor

```
ui_open_panel(panel="pine-editor", action="open")
```

Chờ 3 giây để editor load xong trước khi làm bước tiếp.

### Bước 4 – Nạp Pine Script (nếu có code)

Nếu người dùng cung cấp code Pine Script, gọi:
```
pine_set_source(source="<CODE>")
```

Nếu `pine_set_source` thất bại với lỗi "Could not open Pine Editor" → quay lại Bước 3, chờ thêm 2s rồi thử lại.

### Bước 5 – Compile và lưu

Gọi theo thứ tự:
1. `pine_smart_compile()` – kiểm tra lỗi (`has_errors` phải là `false`)
2. Nếu có lỗi → đọc lỗi, sửa code, quay lại Bước 4
3. `pine_compile()` – lưu indicator
4. `ui_keyboard(key="Enter")` – xác nhận save dialog

### Bước 6 – Đóng Pine Editor

Thử đóng bằng TradingView MCP:
```
ui_open_panel(panel="pine-editor", action="close")
```

Hoặc click nút X:
```
ui_mouse_click(x=1251, y=33)
```

### Bước 7 – Xác nhận kết quả

Chụp ảnh chart để xác nhận indicator đang chạy:
```
capture_screenshot(region="chart")
```

Hiển thị ảnh cho người dùng xem.

## Lưu ý quan trọng

- Pine Script phải dùng `//@version=6`
- Không dùng `elif` – phải dùng `else if`
- `ta.atr()` phải đặt NGOÀI block conditional
- Không dùng `;` để gộp nhiều lệnh trên 1 dòng trong Pine Script v6
- Nếu `pine_set_source` liên tục thất bại → gọi `ui_open_panel` lại, chờ 3s
