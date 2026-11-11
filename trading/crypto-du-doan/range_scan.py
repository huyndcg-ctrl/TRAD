"""Quét coin đang sideway (range 4H rõ ràng) -> gợi ý long đáy range / short đỉnh range."""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from datetime import date as _date
from pathlib import Path as _Path
OUTDIR = _Path(__file__).resolve().parent / _date.today().isoformat()  # kết quả lưu theo ngày
OUTDIR.mkdir(exist_ok=True)


sys.stdout.reconfigure(encoding="utf-8")
import core          # lõi chung: lọc token cổ phiếu/ETF + coin không chơi
API = "https://fapi.binance.com/fapi/v1/"
STOCK = {'SAMSUNG','MU','META','MSTR','KORU','DRAM','NVDA','TSLA','COIN','HOOD','AAPL','AMZN','GOOGL','CRCL','INTC','PLTR','AMD',
         'EWY','TQQQ','QQQ','SPY','XAG','XAU','LITE','SNDK','ORCL','MSFT','AVGO','NFLX','BABA','TSM','SKHYNIX','SKHY','BZ','PUMPBTC'}
SKIP = {'USDCUSDT', 'FDUSDUSDT', 'BTCDOMUSDT'}
N = 36            # số nến 4H xét range (6 ngày)


def get(p):
    for i in range(3):
        try:
            return json.load(urllib.request.urlopen(API + p, timeout=20))
        except Exception as e:
            err = e; time.sleep(1.5)
    raise err


def ema(xs, n):
    a, e = 2 / (n + 1), xs[0]
    for x in xs:
        e = x * a + e * (1 - a)
    return e


def rsi(xs, n=14):
    g = l = 0
    for a, b in zip(xs[-n - 1:-1], xs[-n:]):
        d = b - a; g += max(d, 0); l += max(-d, 0)
    return 100 if l == 0 else 100 - 100 / (1 + g / l)


def analyze(t):
    s = t['symbol']
    try:
        k = get(f'klines?symbol={s}&interval=4h&limit=120')
    except Exception:
        return None
    if len(k) < 100:
        return None
    h = [float(x[2]) for x in k]; l = [float(x[3]) for x in k]; c = [float(x[4]) for x in k]
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    atr = sum(tr[-14:]) / 14
    H, L = h[-N:], l[-N:]
    # biên range dùng mức "được chạm nhiều" thay vì 1 râu duy nhất: lấy phân vị cao/thấp
    hs, ls = sorted(H), sorted(L)
    top, bot = hs[-2], ls[1]                     # bỏ 1 râu cực trị mỗi bên
    width = (top - bot) / bot * 100
    zone = (top - bot) * 0.12
    touch_top = sum(1 for x in H if x >= top - zone)
    touch_bot = sum(1 for x in L if x <= bot + zone)
    closes_in = sum(1 for x in c[-N:] if bot - zone <= x <= top + zone) / N
    slope = (ema(c[-N:], 20) - ema(c[-N - 20:-20], 20)) / atr     # độ dốc ~ số ATR
    e34 = ema(c, 34); e89 = ema(c, 89)
    p = c[-1]
    pos = (p - bot) / (top - bot) * 100
    return dict(sym=s[:-4], p=p, top=top, bot=bot, max_wick=max(H), min_wick=min(L), width=round(width, 1),
                w_atr=round((top - bot) / atr, 1), tt=touch_top, tb=touch_bot, inside=round(closes_in, 2),
                slope=round(slope, 2), pos=round(pos), rsi=round(rsi(c)), atr=atr, atr_pct=round(atr / p * 100, 2),
                trend_d='UP' if e34 > e89 else 'DN', qv=round(float(t['quoteVolume']) / 1e6),
                chg24=float(t['priceChangePercent']))


T = [t for t in get('ticker/24hr') if t['symbol'].endswith('USDT') and t['symbol'] not in SKIP and not core.is_tradfi(t['symbol']) and t['symbol'][:-4] not in core.BLACKLIST]
T = sorted(T, key=lambda t: -float(t['quoteVolume']))[:130]
fund = {x['symbol'][:-4]: float(x['lastFundingRate']) * 100 for x in get('premiumIndex')}
with ThreadPoolExecutor(12) as ex:
    R = [r for r in ex.map(analyze, T) if r]
for r in R:
    r['fund'] = round(fund.get(r['sym'], 0), 4)
json.dump(R, open(OUTDIR / 'range_rows.json', 'w', encoding='utf-8'), ensure_ascii=False)

print('now', datetime.now(timezone.utc).strftime('%d/%m %H:%M UTC'))
btc = next(r for r in R if r['sym'] == 'BTC')
print(f"BTC p={btc['p']:,.0f} range6d {btc['bot']:,.0f}–{btc['top']:,.0f} ({btc['width']}%) pos {btc['pos']}% rsi4h {btc['rsi']} slope {btc['slope']}")

good = [r for r in R if 5 <= r['width'] <= 25 and r['w_atr'] >= 4 and r['tt'] >= 3 and r['tb'] >= 3
        and r['inside'] >= 0.85 and abs(r['slope']) <= 1.5 and r['qv'] >= 25]
print(f"\nRange rõ ràng: {len(good)}/{len(R)} coin")
print("\n=== GẦN ĐÁY RANGE (pos <= 30%) → LONG ===")
for r in sorted([g for g in good if g['pos'] <= 30], key=lambda r: r['pos']):
    print(f"{r['sym']:9} p={r['p']:<10g} range {r['bot']:g}–{r['top']:g} ({r['width']}%, {r['w_atr']} ATR) pos {r['pos']}% | chạm đỉnh {r['tt']} đáy {r['tb']} | rsi {r['rsi']} slope {r['slope']} | 1D {r['trend_d']} | ATR {r['atr_pct']}% fund {r['fund']:+.4f} vol {r['qv']}M | râu {r['min_wick']:g}/{r['max_wick']:g}")
print("\n=== GẦN ĐỈNH RANGE (pos >= 70%) → SHORT ===")
for r in sorted([g for g in good if g['pos'] >= 70], key=lambda r: -r['pos']):
    print(f"{r['sym']:9} p={r['p']:<10g} range {r['bot']:g}–{r['top']:g} ({r['width']}%, {r['w_atr']} ATR) pos {r['pos']}% | chạm đỉnh {r['tt']} đáy {r['tb']} | rsi {r['rsi']} slope {r['slope']} | 1D {r['trend_d']} | ATR {r['atr_pct']}% fund {r['fund']:+.4f} vol {r['qv']}M | râu {r['min_wick']:g}/{r['max_wick']:g}")
print("\n=== GIỮA RANGE (chờ) ===")
print(', '.join(f"{r['sym']}({r['pos']}%)" for r in sorted([g for g in good if 30 < g['pos'] < 70], key=lambda r: r['pos'])))
