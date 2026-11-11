"""LÕI CHUNG cho mọi script quét/backtest: dữ liệu Binance Futures (có cache), chỉ báo, bộ lọc chất lượng coin,
chế độ thị trường. Các script khác import từ đây thay vì tự viết lại.

  get(path)                  gọi API (thử lại 3 lần)
  kl(sym, itv, n)            nến [(t, o, h, l, c, quoteVol, takerBuyQuote)], cache RAM + đĩa (_cache/, 4 phút)
  ema / ema_series / rsi / atr_k / atr_series / pivots / ichimoku / trend
  universe(top, min_vol)     ticker USDT đã bỏ TradFi (cổ phiếu/ETF/hàng hoá), stablecoin
  quality(sym, k4, kd, vol)  (ok, lý do loại, hạng A/B/C) theo quy tắc lọc coin của người dùng
  regime()                   độ rộng top-40 (4H, 1D) + xu hướng BTC 4H
"""
import json, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = Path(__file__).resolve().parent
F = "https://fapi.binance.com"
CACHE = HERE / "_cache"; CACHE_TTL = 240
SKIP = {"USDCUSDT", "FDUSDUSDT", "BTCDOMUSDT", "USDPUSDT", "TUSDUSDT"}
# token cổ phiếu / ETF / hàng hoá (danh sách tay, bổ sung cho phân loại TRADIFI của Binance)
STOCK = set("""SAMSUNG MU META MSTR KORU DRAM NVDA TSLA COIN HOOD AAPL AMZN GOOGL CRCL INTC PLTR AMD EWY TQQQ QQQ SPY XAG XAU LITE SNDK
ORCL MSFT AVGO NFLX BABA TSM SKHYNIX SKHY BZ PUMPBTC QCOM NBIS CL NATGAS NG HG SNXX SOXL SOXS TNA TZA UVXY SQQQ XPT XPD WDC CBRS MVLL
MRVL BE RKLB EWZ CRWV AAOI MUU SPCX PAXG XAUT UNITREE ZHIPU""".split())
# coin người dùng đã nói không chơi (nhỏ / mới / hay bị bơm)
BLACKLIST = set("NIL GTC SAND DODOX Q DOOD CAP BULLA JCT ARIA AIN INIT".split())
WATCH = ("XVG PENGU ZK PIPPIN SENT LAYER ZAMA ASTER TRUMP GIGGLE HYPE BCH ZEC ARKM FARTCOIN ARB FET ADA EIGEN ENA TRX "
         "JUP WLD PUMP FIL DOT RENDER ICP LIT NEAR INJ ETC UNI AVAX AAVE ONDO TAO SAND").split()
MAX_ATR4 = 0.05          # ATR 4H tối đa 5% giá
MIN_VOL = 30e6           # volume 24h tối thiểu
MIN_AGE_DAYS = 180       # niêm yết futures ít nhất 6 tháng
MIN_MEDVOL = 15e6        # volume ngày trung vị 30 ngày (lọc coin chỉ có volume lúc bị bơm)
PUMP_7D = 0.40           # tăng ≥40% trong 7 ngày = vừa bơm

_mem, _lock = {}, threading.Lock()


def get(p):
    err = None
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(F + p, timeout=20))
        except Exception as e:
            err = e; time.sleep(1.2)
    raise err


def kl(sym, itv, n, cache=True):
    key = f"{sym}_{itv}_{n}"
    if cache:
        with _lock:
            if key in _mem:
                return _mem[key]
        f = CACHE / (key + ".json")
        try:
            if time.time() - f.stat().st_mtime < CACHE_TTL:
                r = [tuple(x) for x in json.loads(f.read_text())]
                with _lock:
                    _mem[key] = r
                return r
        except Exception:
            pass
    r = [(int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]))
         for x in get(f"/fapi/v1/klines?symbol={sym}&interval={itv}&limit={n}")]
    if cache:
        with _lock:
            _mem[key] = r
        try:
            CACHE.mkdir(exist_ok=True); (CACHE / (key + ".json")).write_text(json.dumps(r))
        except Exception:
            pass
    return r


def outdir():
    d = HERE / date.today().isoformat(); d.mkdir(exist_ok=True); return d


# ---------------------------------------------------------------- chỉ báo
def ema_series(xs, n):
    a, e, out = 2 / (n + 1), xs[0], []
    for x in xs:
        e = x * a + e * (1 - a); out.append(e)
    return out


def ema(xs, n):
    return ema_series(xs, n)[-1]


def rsi(c, n=14):
    g = sum(max(c[i] - c[i - 1], 0) for i in range(len(c) - n, len(c)))
    d = sum(max(c[i - 1] - c[i], 0) for i in range(len(c) - n, len(c)))
    return 100.0 if d == 0 else 100 - 100 / (1 + g / d)


def tr_series(k):
    return [k[0][2] - k[0][3]] + [max(k[i][2] - k[i][3], abs(k[i][2] - k[i - 1][4]), abs(k[i][3] - k[i - 1][4])) for i in range(1, len(k))]


def atr_k(k, n=14):
    return sum(tr_series(k)[-n:]) / n


def atr_series(k, n=14):
    tr = tr_series(k)
    return [sum(tr[max(0, i - n + 1):i + 1]) / min(n, i + 1) for i in range(len(k))]


def pivots(k, K=3):
    hi, lo = [], []
    for i in range(K, len(k) - K):
        if k[i][2] == max(x[2] for x in k[i - K:i + K + 1]): hi.append(k[i][2])
        if k[i][3] == min(x[3] for x in k[i - K:i + K + 1]): lo.append(k[i][3])
    return hi, lo


def ichimoku(k):
    """Tenkan, Kijun, đỉnh mây, đáy mây, mây xanh? — mây tại nến hiện tại (tính từ 26 nến trước, không lệch)."""
    h = [x[2] for x in k]; l = [x[3] for x in k]
    mid = lambda a, b: (max(h[a:b]) + min(l[a:b])) / 2
    n = len(k); j = n - 26
    sa, sb = (mid(j - 9, j) + mid(j - 26, j)) / 2, mid(j - 52, j)
    return mid(n - 9, n), mid(n - 26, n), max(sa, sb), min(sa, sb), sa > sb


def trend(c):
    e34, e89 = ema(c, 34), ema(c, 89)
    return "UP" if e34 > e89 and c[-1] > e89 else "DN" if e34 < e89 and c[-1] < e89 else "MIX"


# ---------------------------------------------------------------- vũ trụ coin + lọc chất lượng
_info = None


def info():
    """symbol → dict(tradfi, sub, onboard) từ exchangeInfo (cache đĩa 12 giờ)."""
    global _info
    if _info is not None:
        return _info
    f = CACHE / "exchangeInfo.json"
    try:
        if time.time() - f.stat().st_mtime < 43200:
            _info = json.loads(f.read_text()); return _info
    except Exception:
        pass
    try:
        d = get("/fapi/v1/exchangeInfo")
        _info = {s["symbol"]: dict(tradfi=s.get("contractType") != "PERPETUAL" or s.get("underlyingType") != "COIN",
                                   sub=s.get("underlyingSubType") or [], onboard=s.get("onboardDate", 0) // 1000)
                 for s in d["symbols"] if s.get("status") == "TRADING"}
        CACHE.mkdir(exist_ok=True); f.write_text(json.dumps(_info))
    except Exception:
        _info = {}
    return _info


def is_tradfi(sym):
    base = sym[:-4] if sym.endswith("USDT") else sym
    i = info().get(base + "USDT", {})
    return base in STOCK or i.get("tradfi", False) or "RWA" in i.get("sub", [])


def age_days(sym):
    ob = info().get(sym, {}).get("onboard")
    return None if not ob else (time.time() - ob) / 86400


def tier(vol_m):
    """Hạng ưu tiên theo volume 24h (triệu USDT): A ≥100M, B 30–100M, C <30M."""
    return "A" if vol_m >= 100 else "B" if vol_m >= 30 else "C"


def tickers():
    return [t for t in get("/fapi/v1/ticker/24hr") if t["symbol"].endswith("USDT") and t["symbol"] not in SKIP and not is_tradfi(t["symbol"])]


def universe(top=150, min_vol=MIN_VOL, extra=()):
    """Ticker 24h (đã bỏ TradFi/stable), sắp theo volume giảm dần. extra: coin thêm vào dù volume thấp."""
    T = sorted(tickers(), key=lambda t: -float(t["quoteVolume"]))
    ex = {c.upper() + "USDT" for c in extra}
    return [t for i, t in enumerate(T) if (i < top and float(t["quoteVolume"]) >= min_vol) or t["symbol"] in ex]


def quality(sym, k4, kd, vol24):
    """(ok, [lý do loại], hạng). k4/kd: nến 4H/1D (kd ≥ 31 nến). vol24 tính bằng USDT."""
    base = sym[:-4]; why = []
    if is_tradfi(sym): why.append("token cổ phiếu/ETF/hàng hoá")
    if base in BLACKLIST: why.append("trong danh sách không chơi")
    a = age_days(sym)
    if a is not None and a < MIN_AGE_DAYS: why.append(f"coin mới ({a:.0f} ngày)")
    p = k4[-1][4]; atrp = atr_k(k4) / p
    if atrp > MAX_ATR4: why.append(f"ATR 4H {atrp * 100:.1f}% > 5%")
    if vol24 < MIN_VOL: why.append(f"volume {vol24 / 1e6:.0f}M < 30M")
    dv = sorted(x[5] for x in kd[-31:-1])
    med = dv[len(dv) // 2] if dv else 0
    if med < MIN_MEDVOL: why.append(f"volume thường ngày chỉ {med / 1e6:.0f}M")
    if len(kd) >= 9 and kd[-1][4] / kd[-8][4] - 1 >= PUMP_7D: why.append(f"vừa bơm +{(kd[-1][4] / kd[-8][4] - 1) * 100:.0f}%/7 ngày")
    return (not why), why, tier(vol24 / 1e6)


# ---------------------------------------------------------------- chế độ thị trường
def regime(n=40):
    syms = [t["symbol"] for t in sorted(tickers(), key=lambda t: -float(t["quoteVolume"]))[:n]]

    def one(s):
        try:
            c4 = [x[4] for x in kl(s, "4h", 300)[:-1]]; cd = [x[4] for x in kl(s, "1d", 150)[:-1]]
            return ema(c4, 34) > ema(c4, 89), ema(cd, 34) > ema(cd, 89)
        except Exception:
            return None
    with ThreadPoolExecutor(8) as ex:
        R = [r for r in ex.map(one, syms) if r]
    b4 = [x[4] for x in kl("BTCUSDT", "4h", 300)[:-1]]
    u4, u1 = sum(r[0] for r in R), sum(r[1] for r in R)
    return dict(n=len(R), up4=u4, up1=u1, breadth4=u4 / len(R), breadth1=u1 / len(R), btc_up=ema(b4, 34) > ema(b4, 89),
                mode="TĂNG" if u4 / len(R) >= 0.5 else "ĐIỀU CHỈNH")


# ---------------------------------------------------------------- tiện ích file kèo
def newest(name):
    """File `name` trong thư mục ngày mới nhất có nó (vd picks.json)."""
    for d in sorted((x for x in HERE.iterdir() if x.is_dir() and len(x.name) == 10 and x.name[:2] == "20"), reverse=True):
        if (d / name).exists():
            return d / name
    return None


def num(x):
    """Số → chuỗi gọn, không dùng dạng mũ (72690 → 72,690; 0.00562 → 0.00562)."""
    if abs(x) >= 10000:
        return f"{x:,.0f}"
    return f"{x:.10f}".rstrip("0").rstrip(".")
