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

**Trước khi khởi động, kiểm tra đã có TradingView chạy chưa** (`tasklist | findstr /i tradingview`):
- Có process nhưng cổng 9222 không trả lời (`curl -s -m 3 http://127.0.0.1:9222/json/version` rỗng) → TradingView đang mở KHÔNG có cổng debug. **Không tự tắt** app của người dùng: báo họ đóng TradingView rồi chạy lại skill này.
- Không có process → khởi động như dưới.
- Sau khi kết nối, nếu trang có hộp "Phiên bị ngắt kết nối" (tài khoản đang mở trên máy khác): **KHÔNG bấm "Kết nối"**, dừng và báo người dùng.
- Không click theo toạ độ (màn hình scale 125%), không dùng `draw_clear`, không sửa/xoá alert và hình vẽ của người dùng.

Máy này có 2 bản TradingView. Bản portable (mặc định của skill này):
```
Start-Process "C:\Users\dell\TradingView-portable\TradingView.exe" -ArgumentList "--remote-debugging-port=9222"
```

Bản Microsoft Store (routine 8h và các script trong `crypto-du-doan` dùng bản này vì nó giữ phiên đăng nhập + alert):
```
$pkg = Get-AppxPackage -Name '*TradingView*' | Select -First 1; $exe = Join-Path $pkg.InstallLocation 'TradingView.exe'; $appId = (Get-AppxPackageManifest $pkg).Package.Applications.Application.Id; Invoke-CommandInDesktopPackage -PackageFamilyName $pkg.PackageFamilyName -AppId $appId -Command $exe -Args '--remote-debugging-port=9222'
```
Chỉ mở MỘT bản (hai bản cùng tài khoản sẽ đá phiên của nhau). Việc liên quan alert/kèo → dùng bản Store; chỉ nạp Pine thử nghiệm → bản nào đang mở thì dùng bản đó.

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
