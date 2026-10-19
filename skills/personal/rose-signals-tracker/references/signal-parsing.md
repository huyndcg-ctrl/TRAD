# Cách bóc tín hiệu từ post kênh Rose

Kênh Rose đăng rất nhiều, phần lớn là "noise". Mục tiêu: lọc ra **tín hiệu vào
lệnh** và **cập nhật tín hiệu cũ**, bỏ qua phần hô hào.

## 1. Tín hiệu VÀO LỆNH (tạo entry + vẽ line)

Post có `#TICKER` (hoặc tên coin viết hoa) kèm một trong các cụm:

| Cụm trong post | Ý nghĩa | Hướng |
|---|---|---|
| `#X BULLISH`, `okay bullish #X` | mở/khẳng định long | long |
| `#X BULLISH more`, `add more`, `adding more`, `#X ADD MORE` | gom thêm (giá vẫn trong vùng vào) | long |
| `Spot buy #X`, `Spot HOLD #X`, `accumulate` | mua spot | long |
| `#X Buy Setup`, `buy zone A-B` | có vùng vào rõ | long |
| `#X SHORT` | mở short | short |
| `Long #X SL <giá>` | long kèm SL cụ thể | long |

Ưu tiên đọc **số** trong post: `TP 10$`, `SL 3.1`, `buy zone 230-235`,
`Long #BTC SL 754400` → lấy nguyên.

## 2. CẬP NHẬT tín hiệu cũ (đổi trạng thái, không tạo mới)

| Cụm | Hành động |
|---|---|
| `CLOSED #X`, `#X closed`, `take profit`, `TP hit` | status → `closed` |
| `#X SHORT` khi đang có long `active` | đảo chiều → long cũ `invalidated`, tạo short mới |
| `#X deviation`, `cycle top`, `distribution`, `be careful` | status → `watch` (giảm độ tin cậy) |
| `Don't short #X`, `still not late to add` | giữ `active`, ghi chú "còn hiệu lực" |
| Giá đã thủng invalidation đã ghi | status → `invalidated` (kể cả khi Rose chưa nói) |

## 3. KHÔNG phải tín hiệu (chỉ ghi "context")

- So sánh chu kỳ: "Buying X today is like buying BTC 2020"
- Marketcap target: "100B$ club", "first 1000$"
- Ảnh PnL / bảng win-rate / "From 14k to 450k"
- Câu hỏi tu từ: "Do you understand?", "What is next?"
- Post về BTC.D / USDT.D / macro chung
- Meme, ảnh nhân vật, "if u know u know"

## 4. Gộp post

Rose hay đăng 3–5 post liên tiếp cùng 1 ý trong vài phút (có bản edit, bản
reply). Gộp các post cùng coin + cùng hướng trong cùng ngày thành **một** tín
hiệu, `source_posts` liệt kê tất cả num.

## 5. Đọc ảnh chart

Với mỗi tín hiệu vào lệnh có ảnh: `Read` file `rose-tracker/img/<num>_<i>.jpg`.
Tìm:
- Đường ngang màu (thường trắng/vàng) = mức entry hoặc trigger.
- Box/hình chữ nhật = vùng tích luỹ; cạnh trên = mức breakout.
- Mũi tên / chữ "entry", "buy", "target".
- Tên sàn góc trên trái (Rose hay dùng Coinbase/Binance) — đối chiếu khi resolve symbol.

Nếu ảnh mờ/không đọc được mức → suy ra từ OHLCV như mô tả trong SKILL.md bước 4.2.
