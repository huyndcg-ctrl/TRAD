---
name: rose-signals-tracker
description: >-
  Quét kênh Telegram Rose Signals Premium (@RoseSignalsPremium) để bắt tín hiệu
  trade mới và cập nhật tín hiệu cũ, rồi tự động: đọc chart lấy vùng entry, thêm
  mã vào watchlist "rose call" + vẽ đường entry lên layout "BAMBAM v2 ONLY" trên
  TradingView, phân tích nên vào hay không, và đề xuất điểm buy/sell. Chạy gia
  tăng (incremental) — chỉ xử lý post mới kể từ lần quét gần nhất, có file lịch
  sử chống quét trùng. LUÔN dùng skill này khi người dùng nói "quét rose",
  "check rose", "update rose call", "scan tín hiệu rose", "rose có gì mới không",
  "cập nhật tín hiệu", hoặc khi routine 2 ngày/lần kích hoạt. Cũng dùng khi người
  dùng nhắc tới kênh Rose / RoseSignalsPremium và muốn theo dõi call của họ.
---

# Rose Signals Tracker

Theo dõi kênh **@RoseSignalsPremium** và biến các "call" (thường chỉ là ảnh chart
+ dòng "#COIN BULLISH / add more", hiếm khi có số entry) thành một quy trình lặp
lại: quét → bóc tín hiệu → lấy entry từ chart → cập nhật TradingView → phân tích →
ra quyết định buy/sell.

Kênh là **public** — đọc qua bản web `https://t.me/s/RoseSignalsPremium`, **không
cần đăng nhập**. Không bao giờ tự đăng nhập Telegram; nếu kênh chuyển private thì
dừng lại và báo người dùng.

## File trạng thái (trong thư mục làm việc)

| File | Ai ghi | Nội dung |
|---|---|---|
| `rose-tracker/scan-history.json` | script `--commit` | mã post cuối đã quét (`last_message_num`) + thời điểm |
| `rose-tracker/signals.json` | Claude | danh sách tín hiệu đang theo dõi + trạng thái (xem schema dưới) |
| `rose-tracker/reports/YYYY-MM-DD.md` | Claude | báo cáo mỗi lần quét |
| `rose-tracker/img/` | script `--download-images` | ảnh chart của các post (xem để đọc đường Rose vẽ) |

`signals.json` — mỗi phần tử:
```json
{
  "coin": "TAO", "symbol": "BINANCE:TAOUSDT",
  "first_call": "2026-09-07", "last_update": "2026-09-07",
  "direction": "long", "call_type": "reclaim EMA200/MA200 D",
  "entry_line": 236.4, "entry_note": "Daily close > EMA200/MA200",
  "tv_line_id": "oJaRfV",
  "status": "active | invalidated | closed | watch",
  "source_posts": [48169, 48170],
  "verdict": "wait", "buy_zone": [230, 238], "invalidation": 210, "targets": [300, 360]
}
```

## Quy trình

### 0. Kết nối TradingView
Gọi `mcp__tradingview__tv_health_check`. Nếu fail → dùng skill **tradingview-connect**
(one-liner PowerShell, package `31178TradingViewInc.TradingView`) rồi check lại.

### 1. Quét Telegram (incremental)
```bash
python .claude/skills/rose-signals-tracker/scripts/scan_rose.py --download-images rose-tracker/img
```
- Tự đọc `scan-history.json`; chỉ trả post có `num > last_message_num`.
- Lần đầu (chưa có history) → mặc định quét 3 ngày; đổi bằng `--days N`.
- **Chưa** commit history ở bước này — chỉ commit ở bước 6 sau khi xử lý xong.

### 2. Không có gì mới → dừng
Nếu `count == 0`: ghi 1 dòng vào report của ngày (`"Không có post mới kể từ #<id>."`)
và kết thúc. Không đụng vào TradingView.

### 3. Bóc tín hiệu từ post mới
Đọc `references/signal-parsing.md` để biết cách phân loại. Tóm tắt:
- **Tín hiệu vào lệnh**: có `#COIN` + một trong `BULLISH / LONG / BUY / add more /
  bullish more / spot buy / accumulate` (hoặc `SHORT` cho lệnh bán).
- **Cập nhật tín hiệu cũ**: `CLOSED #COIN`, `#COIN SHORT` sau khi đã long (đảo
  chiều), "cycle top", "deviation", "take profit", "SL".
- **Chỉ là luận điểm / hô hào**: so sánh với chu kỳ trước, marketcap target, ảnh
  meme PnL → KHÔNG tạo tín hiệu, chỉ ghi 1 dòng "context" trong report.
- Với mỗi tín hiệu vào lệnh, **mở ảnh chart của post** (`rose-tracker/img/<num>_*.jpg`)
  bằng Read để xem Rose vẽ đường/box entry ở đâu.

### 4. Lấy entry + cập nhật TradingView
Cho mỗi tín hiệu vào lệnh mới, hoặc tín hiệu cũ có thay đổi:

1. **Resolve symbol** theo bảng ở cuối file (ưu tiên BINANCE spot → OKX → KUCOIN/MEXC).
   Dùng `mcp__tradingview__symbol_search` khi không chắc.
2. **Xác định đường entry** — theo thứ tự ưu tiên:
   - Số entry Rose ghi thẳng trong text → dùng luôn.
   - Đường/box Rose vẽ trong ảnh chart → ước lượng mức giá đó.
   - Không có → mức kỹ thuật hợp lý nhất từ `data_get_ohlcv` (D):
     đỉnh vùng tích luỹ mà post nói "breakout", hoặc EMA200/MA200 D nếu post nói
     "reclaim/closed above", hoặc swing-low gần nhất nếu post nói "local support".
   - Ghi rõ trong report cơ sở nào được dùng ("Rose ghi số" / "đọc từ ảnh" / "suy ra").
3. **Watchlist**: chọn list `rose call` (menu watchlist). Nếu symbol chưa có →
   thêm bằng nút "+" (dialog *Thêm Mã*, gõ full symbol, bấm dấu +). Xác nhận bằng
   `mcp__tradingview__watchlist_get`.
4. **Layout**: `mcp__tradingview__layout_switch` → `"BAMBAM v2 ONLY"`.
5. **Vẽ đường**: set symbol, rồi `draw_shape` `horizontal_line` tại `price = entry`,
   `overrides` `{"linecolor":"#2962ff","linewidth":2,"linestyle":2,"showLabel":true,"textcolor":"#2962ff"}`,
   `text = "Rose call <ngày>: <cơ sở> -> entry ~<giá>"`. Màu xám `#787b86` nếu chỉ
   là luận điểm chứ không phải call trade thật. Lưu `entity_id` vào `signals.json`.
   Nếu tín hiệu cũ đổi entry → xoá đường cũ (`draw_remove_one` theo `tv_line_id`)
   rồi vẽ lại.
   Layout có autosave — không cần Ctrl+S, nhưng kiểm tra lại bằng screenshot.

### 5. Phân tích: nên vào hay không
Trên layout `BAMBAM v2 ONLY` (khung 3D), với mỗi symbol:
- `mcp__tradingview__data_get_study_values` → đọc các chỉ báo có sẵn:
  **BAMBAM v2 with VWAP Bands** (EMA Regime, VWAP L1/U1/L2/U2), **Ichimoku
  Theories [LuxAlgo]** (Kijun, SpanA/B), **FVG & OB BY SƠN DUBAI**, **TK Cross >
  EMA200 Strat**.
- Tự bổ sung: đọc `data_get_ohlcv` khung 1D và 3D, xác định
  giá vs EMA200 D, cấu trúc HH/HL, vị trí so với vùng tích luỹ, volume breakout.
- Bối cảnh BTC: `quote_get` `OKX:BTCUSDT.P` + xu hướng D (BTC yếu → hạ độ tin cậy
  các call altcoin).
- Đọc `references/analysis-checklist.md` để chấm điểm.

### 6. Quyết định buy/sell + chốt sổ
Cho mỗi tín hiệu, đưa ra:
- **Verdict**: `Vào ngay` / `Chờ retest` / `Chờ xác nhận` / `Bỏ qua` / `Đảo/Thoát`.
- **Buy zone**: vùng giá vào hợp lý (thường = đường entry ± biên, hoặc vùng retest).
- **Invalidation (SL)**: mức làm sai kịch bản (dưới swing low / dưới đường entry
  một khoảng theo ATR).
- **Targets**: 1–2 mốc TP (kháng cự kế tiếp / mở rộng Fib / marketcap target Rose nêu).
- Ghi tất cả vào `signals.json` và vào report theo template cuối file.
- Cập nhật trạng thái tín hiệu cũ (còn `active`, đã `invalidated`, đã `closed`).
- **Commit history**: chạy lại script với `--commit` (không cần in ra):
  ```bash
  python .claude/skills/rose-signals-tracker/scripts/scan_rose.py --commit
  ```
- Gửi report cho người dùng (`SendUserFile` file `.md` + screenshot chart chính).

## Routine 2 ngày/lần
Người dùng muốn chạy tự động **2 ngày/lần lúc 08:00**. Dùng skill `schedule`
(hoặc `mcp__scheduled-tasks__create_scheduled_task`) tạo routine:
- prompt: *"Chạy skill rose-signals-tracker: quét update mới của kênh Rose, cập
  nhật TradingView và gửi report."*
- lịch: mỗi 2 ngày, 08:00 giờ địa phương (Asia/Ho_Chi_Minh).
Không tạo routine khi người dùng chưa xác nhận rõ; nếu họ đã yêu cầu thì tạo và
báo lại tên routine.

## Bảng resolve symbol (mã hay gặp ở kênh Rose)

| Coin | Symbol TradingView |
|---|---|
| ZEC | BINANCE:ZECUSDT |
| XMR | KUCOIN:XMRUSDT (Binance đã delist) |
| NEAR | BINANCE:NEARUSDT |
| TAO | BINANCE:TAOUSDT |
| HYPE | OKX:HYPEUSDT (không có Binance spot) |
| ZAMA | BINANCE:ZAMAUSDT |
| MARSCOIN | BINANCE:MARSCOINUSDT (data mỏng, mới list) |
| BTC/ETH/SOL/BNB | BINANCE:<X>USDT |
| Mã lạ / meme | `symbol_search` → chọn sàn thanh khoản cao nhất có lịch sử dài |

## Template report

```markdown
# Rose Signals — quét ngày {YYYY-MM-DD}

Post mới: {n} (từ #{from_id} → #{to_id}). Tín hiệu trade: {k}. Context/hô hào: {m}.

## Tín hiệu mới
### {COIN} — {LONG/SHORT} — {verdict}
- **Rose call**: {ngày} "{trích post}" (post #{num})
- **Entry line**: ~{giá}  ({cơ sở: Rose ghi số / đọc từ ảnh / suy ra})
- **Giá hiện tại**: {giá}  ({Δ%} so với entry)
- **Chỉ báo (BAMBAM v2 layout, 3D)**: EMA Regime {..}; Ichimoku {..}; VWAP {..}; FVG/OB {..}
- **Bối cảnh BTC**: {..}
- **Quyết định**: {Vào ngay/Chờ retest/...} — buy zone {a–b}, SL {x}, TP {t1 / t2}
- TradingView: đã thêm vào "rose call", đã vẽ line (id {entity_id})

## Cập nhật tín hiệu cũ
### {COIN}: {active→invalidated / closed / đảo chiều} — {lý do + hành động}

## Context (không tạo tín hiệu)
- {gạch đầu dòng ngắn}
```

## Nguyên tắc
- Đây là **theo dõi + phân tích**, không phải lời khuyên đầu tư — luôn ghi rõ khi
  entry là do mình suy ra chứ không phải Rose công bố.
- Không đặt lệnh, không chuyển tiền. Chỉ vẽ, chỉ phân tích.
- Kênh Rose nhiều post đảo chiều nhanh (long rồi short trong 1–2 ngày) → luôn kiểm
  tra post *mới nhất* của mỗi coin trước khi kết luận hướng.
