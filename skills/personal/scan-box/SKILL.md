---
name: scan-box
description: |
  Quét danh sách coin crypto qua TradingView Desktop để tìm mô hình BOX trên khung 1H: giá tạo hộp tích luỹ đi ngang → quét thanh khoản (râu thủng đáy hộp rồi rút lại) → phá cạnh trên → retest cạnh trên để LONG. Trả về bảng hộp hiện tại của từng coin (đáy/đỉnh, vị trí giá trong hộp, đã sweep chưa) + các setup đang retest kèm Entry/SL/TP/R:R, và theo dõi kết quả setup của lần quét trước. Dùng khi người dùng nói "tìm box", "quét box", "có cái hộp nào không", "tìm box của các con coin", "mô hình hộp", "quét liq rồi phá đỉnh", "long retest cạnh trên", hoặc gửi ảnh chart có hộp + sweep và bảo tìm coin tương tự.
---

# Scan Box — hộp 1H, quét thanh khoản, phá đỉnh, retest

Skill này đóng gói lại quy trình quét box đã chạy nhiều lần (22/10, 27/10, 28/10/2026): lấy 300 nến 1H của từng coin qua TradingView MCP, dùng script Python tự tìm hộp, sweep và breakout, rồi báo cáo bằng tiếng Việt.

## Mô hình cần tìm

```
        ┌───── retest cạnh trên → LONG ─────▶ TP = đỉnh + chiều cao hộp
 đỉnh ──┤▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔╱▔▔╲_╱
        │   hộp đi ngang 2–10 ngày    ╱      ← nến close phá đỉnh
 đáy  ──┤▁▁▁▁▁▁▁▁╷▁▁▁▁▁▁▁▁▁▁╱
                 │← sweep: râu thủng đáy ≥1%, close lại trong hộp ≤6 nến
```

## Định nghĩa định lượng (đã cố định trong script)

| Thành phần | Quy tắc |
|---|---|
| Khung | 1H, 300 nến, **bỏ nến cuối đang chạy**, chỉ dùng nến đã đóng |
| Hộp | Dài 48–240 nến (2–10 ngày). Đỉnh = percentile 95 của high. Đáy = percentile 5 của close. Biên độ ≤15%. ≥90% close nằm trong [đáy −1.5%, đỉnh +0.3%]. Độ dốc hồi quy × độ dài ≤ 60% chiều cao hộp (phải đi ngang, không phải kênh dốc) |
| Trước hộp | Đỉnh 72 nến trước hộp ≥ đỉnh hộp +3% (giá đi từ trên xuống rồi tích luỹ) |
| Sweep | Low < đáy −1%, sau đó có nến close > đáy trong ≤6 nến |
| Breakout | Nến ngay sau hộp close > đỉnh +0.2%. Ghi volume nến phá / volume trung bình hộp |
| Entry | Đỉnh hộp (cạnh trên) |
| SL | max(giữa hộp, đỉnh − 40% chiều cao) |
| TP | Đỉnh + chiều cao hộp → R:R chuẩn = 2.5 |

**Trạng thái setup (theo khoảng cách giá tới cạnh trên):**
- **A**: −2% đến +2%. Đang retest, đây là setup chính.
- **B**: +2% đến +8%. Đã chạy, R:R vào lúc này kém.
- **D**: trên +8%. Bỏ qua.
- **WEAK**: đã rơi lại vào hộp nhưng còn trên giữa hộp.
- **FAIL**: dưới giữa hộp. Bỏ.
- **C**: đã sweep, chưa phá đỉnh. Đưa vào danh sách chờ.

Chỉ báo các breakout trong 72 nến gần nhất.

## Bước 1 — Kết nối TradingView

1. Gọi `tv_health_check`.
2. Nếu `cdp_connected: false`, khởi động lại bằng PowerShell như trong skill `scan-channel` (Bước 1). Lưu ý tên gói AppX phải match `'*TradingView*'`, không phải `'TradingView*'`.
3. Gọi `chart_get_state` một lần để ghi lại symbol và khung hiện tại. Cuối phiên trả chart về đúng trạng thái này.

## Bước 2 — Danh sách coin

- Nếu người dùng nêu coin cụ thể thì quét các coin đó.
- Nếu họ chỉ nói "các con coin", dùng danh sách mặc định 44 mã (đúng symbol/sàn đã dùng):

```
OKX:BTCUSDT.P OKX:ETHUSDT.P OKX:SOLUSDT.P OKX:BNBUSDT.P OKX:XRPUSDT.P OKX:DOGEUSDT.P
OKX:ADAUSDT.P OKX:AVAXUSDT.P OKX:DOTUSDT.P OKX:LTCUSDT.P OKX:BCHUSDT.P OKX:ETCUSDT.P
OKX:UNIUSDT.P OKX:AAVEUSDT.P OKX:SUIUSDT.P OKX:TAOUSDT.P OKX:ONDOUSDT.P OKX:PUMPUSDT.P
OKX:HYPEUSDT.P OKX:ENAUSDT.P OKX:JUPUSDT.P OKX:PENGUUSDT.P OKX:PEPEUSDT.P OKX:BONKUSDT.P
OKX:WLDUSDT.P OKX:ARBUSDT.P OKX:FILUSDT.P OKX:ICPUSDT.P OKX:RENDERUSDT.P OKX:TRUMPUSDT.P
OKX:FETUSDT OKX:INJUSDT OKX:ARKMUSDT OKX:ASTERUSDT OKX:LITUSDT
BINANCE:NEARUSDT BINANCE:LINKUSDT BINANCE:WUSDT BINANCE:ZECUSDT BINANCE:CAKEUSDT
BINGX:FARTCOINUSDT BYBIT:MNTUSDT.P MEXC:XMRUSDT MEXC:EIGENUSDC
```

## Bước 3 — Lấy nến 1H

Dùng thư mục ngắn `C:\Users\dell\tvbox\`. Đường dẫn scratchpad quá dài sẽ vượt giới hạn 260 ký tự của Windows và Python báo lỗi `FileNotFoundError`. Mỗi lần quét ghi vào một thư mục mới đặt theo ngày giờ (vd `h1_2810_14`), giữ lại thư mục lần trước để so sánh.

```bash
node C:/Users/dell/.claude/skills/scan-box/scripts/fetch_bars.mjs C:/Users/dell/tvbox/h1_<ddmm_hh> 60 300 <SYM1> <SYM2> ...
```

- Script `fetch_bars.mjs` import trực tiếp `C:/Users/dell/tradingview-mcp/src/core/index.js`. Với mỗi mã, nó đổi symbol, đọc nến 2 lần và kiểm tra symbol/khung không bị đổi giữa chừng. Nếu lỗi thì thử lại tối đa 3 lần.
- Mỗi dòng log `OK` cần có `dt=3600`. Mã nào in `FAIL` hoặc `MISMATCH` thì chạy lại riêng mã đó.
- Với 44 mã, nên chạy nền (`run_in_background`) vì mất vài phút.

## Bước 4 — Chạy quét

```bash
python C:/Users/dell/.claude/skills/scan-box/scripts/box_scan.py C:/Users/dell/tvbox/<thư_mục_mới> [C:/Users/dell/tvbox/<thư_mục_lần_trước>]
```

Script cần `numpy`. Với 44 mã có thể mất vài phút, nên chạy nền. Kết quả gồm:
1. **RETEST / BREAKOUT**: trạng thái A/B/C/WEAK, hộp, sweep, nến phá, volume phá, khoảng cách tới đỉnh, Entry/SL/TP, R:R chuẩn và `rr_now` (R:R nếu vào ở giá hiện tại).
2. **HỘP HIỆN TẠI** của từng coin, sắp theo vị trí trong hộp: TRONG_HOP / TREN_CANH_TREN / THUNG_DAY, đã sweep chưa. Nếu có thư mục cũ thì đánh dấu `DOI:` (đổi trạng thái) và `SWEEP_MOI`.
3. Danh sách mã không tìm được hộp.

## Bước 5 — Theo dõi setup lần trước

Nếu lần quét trước đã đưa setup (Entry/SL/TP), duyệt các nến 1H đã đóng kể từ lúc báo setup:
- Có khớp entry không (low ≤ entry).
- Chạm SL hay TP trước. Nếu cùng một nến chạm cả hai thì tính SL.
- Max high, min low, giá hiện tại.

Báo cả hai kịch bản: vào sớm bằng lệnh limit ở cạnh trên, và vào sau khi nến 1H đóng trên cạnh trên. Bài học HYPE 27/10: vào sớm bị quét SL bằng râu, chờ nến đóng thì vẫn lời.

## Bước 6 — Xác nhận và trả chart

- Với 1–3 setup A tốt nhất, có thể `chart_set_symbol` + `chart_set_timeframe 60` + `capture_screenshot` để xem bằng mắt (hộp có thật sự rõ không, có kháng cự khung lớn ngay trên không).
- Kiểm tra hộp lớn bao ngoài: nếu hộp nhỏ nằm trong một hộp lớn, đỉnh hộp lớn là kháng cự gần, ghi chú lại.
- Cuối cùng trả chart về symbol/khung ghi ở Bước 1.

## Bước 7 — Báo cáo (tiếng Việt, gọn)

1. Dòng đầu: nến 1H đã đóng đến mấy giờ (giờ VN, UTC+7).
2. **Kết quả setup lần trước**: TP / SL / đang mở, bao nhiêu %.
3. **Bảng retest** (state A, kèm C nếu đáng chú ý): Coin | Giá | Entry | SL | TP | Volume phá | Ghi chú (cách cạnh trên bao nhiêu %, R:R tại giá hiện tại, cản hộp lớn). Ưu tiên `rr_now` cao, volume phá ≥1.2x. Đánh dấu rõ khi volume yếu (<1x) hoặc khi giá đã chạy xa cạnh trên (`rr_now` < 1.5).
4. **Sát cạnh trên, chờ phá**: coin, đỉnh hộp, cách bao nhiêu %, đã sweep chưa.
5. **Sát đáy, dễ thủng**: coin ở vị trí <15% trong hộp.
6. **So với lần trước**: thủng đáy, sweep mới, hộp mới.
7. Ghi chú rủi ro.

## Nguyên tắc bắt buộc

- **Chỉ dùng nến đã đóng.** Không kết luận "gãy hỗ trợ" hay "phá đỉnh" từ nến đang chạy (bài học SOL: nến chưa đóng 116.91, đóng ở 117.86).
- Khuyên chờ **nến 1H đóng trên cạnh trên** rồi mới vào, hoặc nếu đặt limit thì chấp nhận rủi ro bị râu quét.
- **Rủi ro tương quan:** khi cả thị trường cùng sweep một lúc, các setup thường thất bại cùng nhau (22/10: ENA, JUP, PENGU, W, BNB cùng dính SL). Nếu BTC đang thủng hộp của nó thì hạ mức tin cậy toàn bộ.
- Đây là sàng lọc kỹ thuật tự động, không phải lời khuyên đầu tư cá nhân. Không đặt lệnh, không nhập thông tin tài khoản.
- **Lọc chất lượng coin trước khi đề xuất setup**: chạy `cd C:/Users/dell/Desktop/trad/crypto-du-doan && PYTHONIOENCODING=utf-8 python -c "import core,sys; V={t['symbol']:float(t['quoteVolume']) for t in core.get('/fapi/v1/ticker/24hr')}; [print(c, core.quality(c+'USDT', core.kl(c+'USDT','4h',300), core.kl(c+'USDT','1d',150), V.get(c+'USDT',0))) for c in sys.argv[1:]]" COIN1 COIN2`. Coin không đạt (coin mới, vừa bơm, ATR 4H > 5%, token cổ phiếu/ETF, volume mỏng) vẫn liệt kê hộp nhưng ghi "không vào lệnh" và không đưa vào mục setup. Coin không có trên Binance Futures thì ghi "chưa lọc được".
- Setup LONG chỉ là ứng viên: ghi rõ **CHƯA BUY** cho tới khi có alert ✅. BTC 4H giảm (xem dòng đầu của `python scan_all.py`) → nói thẳng "không buy".
- `alert_create` của MCP trên máy này trả `price_set:false`, không dùng. Muốn đặt alert: ghi setup vào `crypto-du-doan/YYYY-MM-DD/picks.json` rồi `python alerts.py` → `python alerts.py --apply` (tạo ⏳/✅/❌ đúng mẫu chữ; xem docstring `alerts.py`). Lưu ý mô hình hộp 1H chưa được backtest; alert ✅ của `alerts.py` tính theo nến 4H đóng.
