"""KẾT HỢP indicator layout BAMBAM (TradingView) + phân tích kỹ thuật riêng → chấm điểm & lên kèo 4H.

Phân vai:
  KHUNG LỚN (Python, Binance): EMA34/89/200 khung 1D + EMA34/89 4H, Ichimoku 4H (tự tính, không lệch 26 nến),
                               RSI/ATR 4H, volume (up/down, OBV, taker), cấu trúc HL/LH, BTC mood.
  TRADINGVIEW (đọc qua CDP cổng 9222, layout đang mở phải là BAMBAM v2 ONLY, khung 4H):
      Sơn Dubai v2 : MUA/BÁN OB, FVG, LIQ, ★A+, OTE  → vùng vào / vật cản / STL theo cấu trúc
      Swing VP      : POC (đường liền), VAH/VAL (đứt) + cờ SwingVP BUY/SELL → vùng giá trị
      BAMBAM v2     : dải VWAP L1/L2/U1/U2, EMA Regime, nhãn ◆ BUY/◆ SELL → vùng vào / TP
Quy tắc:
  - Chỉ LONG khi 1D: EMA34 > EMA89 và giá > EMA89 1D. Chỉ SHORT khi ngược lại. Còn lại = đứng ngoài.
  - Entry = cụm ≥2 mức hỗ trợ (EMA 4H, MUA OB/FVG, VWAP L1, VAL/POC, OTE) trong 0.5 ATR, cách giá ≤ 2.5 ATR.
  - STL = dưới đáy cụm/OB − 0.3 ATR, tối thiểu 1 ATR 4H. TP = vật cản kế tiếp (BÁN OB, VWAP U1/U2, POC/VAH, LIQ, đỉnh 30 nến).
  - BÁN OB nằm giữa entry và TP1 (cách < 1 ATR trên giá) → trừ điểm nặng.
Chạy:  python bambam_confluence.py            (watchlist mặc định)
       python bambam_confluence.py AVAX ENA   (coin tuỳ chọn)
Kết quả: YYYY-MM-DD/bambam_confluence.json + .md . Chart được trả về symbol/khung ban đầu khi xong.
"""
import asyncio, json, sys, time, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import websockets

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
OUTDIR = HERE / date.today().isoformat(); OUTDIR.mkdir(exist_ok=True)
F = "https://fapi.binance.com"
HTF_OB, HTF_NAME = "480", "8H"   # khung lớn để lấy OB (Sơn Dubai không vẽ trên 1D)
WATCH = ("BTC ETH SOL BNB XRP DOGE SUI LINK AVAX AAVE ENA WLD DOT NEAR APT FIL ICP ONDO TAO HYPE INJ ARB "
         "FET TIA SEI OP UNI LTC BCH ADA TRX PENGU PUMP EIGEN ZK RENDER JUP").split()


# ---------------------------------------------------------------- dữ liệu Binance
def get(p):
    for _ in range(3):
        try:
            return json.load(urllib.request.urlopen(F + p, timeout=20))
        except Exception as e:
            err = e; time.sleep(1.2)
    raise err


def kl(sym, itv, n):
    return [(int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7]), float(x[10]))
            for x in get(f"/fapi/v1/klines?symbol={sym}&interval={itv}&limit={n}")]


def ema(xs, n):
    a, e = 2 / (n + 1), xs[0]
    for x in xs:
        e = x * a + e * (1 - a)
    return e


def atr(k, n=14):
    tr = [max(k[i][2] - k[i][3], abs(k[i][2] - k[i - 1][4]), abs(k[i][3] - k[i - 1][4])) for i in range(1, len(k))]
    return sum(tr[-n:]) / n


def rsi(c, n=14):
    g = [max(c[i] - c[i - 1], 0) for i in range(len(c) - n, len(c))]
    d = [max(c[i - 1] - c[i], 0) for i in range(len(c) - n, len(c))]
    return 100 - 100 / (1 + sum(g) / max(sum(d), 1e-12))


def ichimoku(k):
    h = [x[2] for x in k]; l = [x[3] for x in k]
    mid = lambda a, b: (max(h[a:b]) + min(l[a:b])) / 2
    n = len(k)
    tenkan, kijun = mid(n - 9, n), mid(n - 26, n)
    j = n - 26                                     # mây tại nến hiện tại = span tính từ 26 nến trước
    span_a = (mid(j - 9, j) + mid(j - 26, j)) / 2
    span_b = mid(j - 52, j)
    return tenkan, kijun, max(span_a, span_b), min(span_a, span_b), span_a > span_b


def pivots(k, K=3):
    hi, lo = [], []
    for i in range(K, len(k) - K):
        if k[i][2] == max(x[2] for x in k[i - K:i + K + 1]): hi.append(k[i][2])
        if k[i][3] == min(x[3] for x in k[i - K:i + K + 1]): lo.append(k[i][3])
    return hi, lo


def htf(sym):
    d = kl(sym, "1d", 300); h4 = kl(sym, "4h", 300)
    cd = [x[4] for x in d]; c4 = [x[4] for x in h4]; v4 = [x[5] for x in h4]; tb4 = [x[6] for x in h4]
    a4 = atr(h4); p = c4[-1]
    up = sum(v4[i] for i in range(-20, 0) if c4[i] >= c4[i - 1]); dn = sum(v4[i] for i in range(-20, 0) if c4[i] < c4[i - 1])
    obv = 0; ob = []
    for i in range(-40, 0):
        obv += v4[i] if c4[i] > c4[i - 1] else -v4[i] if c4[i] < c4[i - 1] else 0; ob.append(obv)
    ph, pl = pivots(h4[-60:])
    t, kj, ctop, cbot, green = ichimoku(h4)
    return dict(p=p, atr=a4,
                e34d=ema(cd, 34), e89d=ema(cd, 89), e200d=ema(cd, 200) if len(cd) >= 200 else None,
                e34=ema(c4, 34), e89=ema(c4, 89), e200=ema(c4, 200),
                tenkan=t, kijun=kj, ctop=ctop, cbot=cbot, cgreen=green,
                rsi4=rsi(c4), rsid=rsi(cd), ud=up / max(dn, 1e-9), obv_up=ob[-1] > ob[-20],
                volx=v4[-2] / (sum(v4[-32:-2]) / 30), buy=sum(tb4[-6:-1]) / max(sum(v4[-6:-1]), 1e-9) * 100,
                hl=len(pl) >= 2 and pl[-1] > pl[-2], lh=len(ph) >= 2 and ph[-1] < ph[-2],
                hi30=max(x[2] for x in h4[-31:-1]), lo30=min(x[3] for x in h4[-31:-1]),
                piv_hi=ph[-3:], piv_lo=pl[-3:])


# ---------------------------------------------------------------- đọc TradingView qua CDP
JS_INSTALL = r"""
window.__bbc = function(){
 var m=window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().model();
 function vals(o){var a=[];if(!o)return a;(o instanceof Map?o:new Map(Object.entries(o))).forEach(function(v){a.push(v)});return a}
 function prims(s,kind,key){try{return vals(s._graphics._primitivesCollection[kind].get(key).get(false)._primitivesDataById)}catch(e){return []}}
 function find(re){return m.dataSources().find(function(x){try{return re.test(x.metaInfo().description)}catch(e){return false}})}
 var out={sym:m.mainSeries().symbol(),res:m.mainSeries().interval()};
 var sd=find(/DUBAI/), vp=find(/Swing VP/), bb=find(/BAMBAM/);
 // giá trị plot + cờ alert 6 nến gần nhất
 [['sd',sd],['vp',vp],['bb',bb]].forEach(function(pair){var s=pair[1];if(!s)return;var mi=s.metaInfo(),d=s.data(),li=d.lastIndex(),o={},f={};
   mi.plots.forEach(function(p,i){var t=(mi.styles&&mi.styles[p.id]&&mi.styles[p.id].title)||p.id;var r=d.valueAt(li);if(r&&r[i+1]!=null&&isFinite(r[i+1]))o[t]=r[i+1];
     if(p.type==='alertcondition'){var hit=0;for(var j=0;j<6;j++){var rr=d.valueAt(li-j);if(rr&&rr[i+1])hit=j+1}if(hit)f[t]=hit-1}});
   out[pair[0]+'_v']=o;out[pair[0]+'_flag']=f});
 // x của primitive là chỉ số trong s._graphics._indexes (mỗi study một bảng) → đổi ra số nến trước (ago, âm = vẽ kéo sang tương lai)
 var cur=m.mainSeries().bars().lastIndex();out.li=cur;
 function ago(s,x){var I=s._graphics._indexes;return cur-(I&&I[x]!=null?I[x]:x)}
 if(sd){var bx=prims(sd,'dwgboxes','boxes'),lb=prims(sd,'dwglabels','labels');
   var act=bx.filter(function(b){return ago(sd,b.x2)<=1});
   out.ob=act.filter(function(b){return /OB/.test(b.t)}).map(function(b){return {side:/MUA/.test(b.t)?'bull':'bear',hi:Math.max(b.y1,b.y2),lo:Math.min(b.y1,b.y2),ago:ago(sd,b.x1),t:b.t.replace('\n',' ')}});
   out.fvg=act.filter(function(b){return b.t==='FVG'}).map(function(b){var c=((b.bc>>>0)&0xffffff).toString(16);return {side:/^9[34]b/.test(c)?'bull':'bear',hi:Math.max(b.y1,b.y2),lo:Math.min(b.y1,b.y2),ago:ago(sd,b.x1)}});
   out.sd_lab=lb.map(function(l){return {t:l.t,y:+l.y,ago:ago(sd,l.x)}}).filter(function(l){return l.ago<=12&&/A\+|LIQ|OTE|Eq|BUY|SELL|BOS|CHoCH/.test(l.t)&&!/✕$/.test(l.t)});}
 if(bb){out.bb_lab=prims(bb,'dwglabels','labels').map(function(l){return {t:l.t,y:+l.y,ago:ago(bb,l.x)}}).filter(function(l){return l.ago>=0&&l.ago<=15&&/BUY|SELL/.test(l.t)})}
 if(vp){var ln=prims(vp,'dwglines','lines').filter(function(l){return l.y1===l.y2});
   out.vp={poc:(ln.find(function(l){return l.st==='sol'||l.w>=2})||{}).y1,va:ln.filter(function(l){return l.st!=='sol'&&l.w<2}).map(function(l){return l.y1}).sort()}}
 return out};
window.__bbgo = async function(sym,res){var ch=window.TradingViewApi.activeChart();
 // không dùng callback (setResolution đôi khi không gọi lại) → đặt rồi chờ tới khi chart đổi xong
 if(ch.symbol()!==sym) ch.setSymbol(sym); if(ch.resolution()!==res) ch.setResolution(res);
 for(var w=0;w<30&&!(ch.symbol()===sym&&ch.resolution()===res);w++) await new Promise(function(r){setTimeout(r,300)});
 var last='',same=0;for(var i=0;i<40;i++){await new Promise(function(r){setTimeout(r,500)});var o;try{o=window.__bbc()}catch(e){continue}
   var sig=JSON.stringify([o.li,(o.ob||[]).length,(o.fvg||[]).length,o.vp&&o.vp.poc,o.bb_v&&o.bb_v['VWAP U2']]);
   if(o.sym.indexOf(sym.split(':')[1])>=0&&o.li&&sig===last){if(++same>=3)return o}else same=0;last=sig}
 return window.__bbc()};
'ok'
"""


class CDP:
    async def __aenter__(self):
        tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5))
        url = next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page" and "tradingview.com/chart" in t.get("url", ""))
        self.ws = await websockets.connect(url, max_size=50_000_000); self.n = 0
        return self

    async def __aexit__(self, *a):
        await self.ws.close()

    async def ev(self, expr, timeout=60):
        self.n += 1; mid = self.n
        await self.ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                       "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout))
            if msg.get("id") == mid:
                r = msg.get("result", {})
                if "exceptionDetails" in r:
                    raise RuntimeError(r["exceptionDetails"].get("text"))
                return r.get("result", {}).get("value")


async def read_tv(coins):
    out = {}
    async with CDP() as c:
        if await c.ev("document.body.innerText.includes('Phiên bị ngắt kết nối')"):
            raise SystemExit("TradingView: phiên bị ngắt kết nối — mở lại TradingView trên máy này (KHÔNG bấm 'Kết nối' nếu đang dùng máy khác).")
        orig = await c.ev("(function(){var ch=window.TradingViewApi.activeChart();return [ch.symbol(),ch.resolution()]})()")
        await c.ev(JS_INSTALL)
        try:
            for coin in coins:
                try:
                    o = await c.ev(f"window.__bbgo('BINANCE:{coin}USDT.P','240')", 60)
                    o8 = await c.ev(f"window.__bbgo('BINANCE:{coin}USDT.P','{HTF_OB}')", 60)
                    for x in o.get("ob", []): x["tf"] = "4H"
                    for x in (o8 or {}).get("ob", []): x["tf"] = HTF_NAME
                    o["ob"] = o.get("ob", []) + (o8 or {}).get("ob", [])
                    out[coin] = o
                    print(f"  TV {coin} ✓ (OB 4H+{HTF_NAME}: {len(o['ob'])})", flush=True)
                except Exception as e:
                    print(f"  TV {coin} lỗi: {e}", flush=True)
        finally:
            await c.ev(f"window.__bbgo({json.dumps(orig[0])},{json.dumps(orig[1])})", 60)
    return out


# ---------------------------------------------------------------- chấm điểm + lên kèo
def plan(coin, H, T, btc):
    p, A = H["p"], H["atr"]
    bias = "LONG" if H["e34d"] > H["e89d"] and p > H["e89d"] else "SHORT" if H["e34d"] < H["e89d"] and p < H["e89d"] else None
    r = dict(coin=coin, p=p, atr=A, bias=bias or "ĐỨNG NGOÀI", score=0, why=[], warn=[])
    if not bias:
        r["why"].append("1D EMA34/89 không cùng phía giá → không có xu hướng khung lớn"); return r
    L = bias == "LONG"; sgn = 1 if L else -1
    add = lambda pts, msg: (r.__setitem__("score", r["score"] + pts), (r["why"] if pts > 0 else r["warn"]).append(f"{pts:+d} {msg}"))
    # 1) khung lớn
    add(2, f"1D xu hướng {'tăng' if L else 'giảm'} (EMA34 {H['e34d']:.4g} / EMA89 {H['e89d']:.4g})")
    if (p - H["e34d"]) * sgn > 0: add(1, "giá cùng phía EMA34 1D")
    if (H["e34"] - H["e89"]) * sgn > 0: add(1, "4H EMA34/89 cùng chiều")
    else: add(-1, "4H EMA34/89 ngược chiều 1D")
    if (btc == "UP" and not L) or (btc == "DN" and L): add(-2, f"BTC 4H đang {btc}, ngược chiều kèo")
    # 2) Ichimoku 4H
    if (L and p > H["ctop"]) or (not L and p < H["cbot"]): add(1, "ngoài mây Ichimoku 4H đúng phía")
    elif H["cbot"] <= p <= H["ctop"]: add(-1, f"giá trong mây Ichimoku 4H ({H['cbot']:.4g}–{H['ctop']:.4g})")
    else: add(-2, "giá sai phía mây Ichimoku 4H")
    if (H["tenkan"] - H["kijun"]) * sgn > 0: add(1, "Tenkan/Kijun 4H cùng chiều")
    # 3) volume + động lượng
    if (L and H["ud"] > 1.2 and H["obv_up"]) or (not L and H["ud"] < 0.83 and not H["obv_up"]): add(1, f"volume ủng hộ (up/down {H['ud']:.2f}, OBV)")
    if (L and H["buy"] < 46) or (not L and H["buy"] > 54): add(-1, f"taker 5 nến 4H ngược chiều ({H['buy']:.0f}% mua)")
    if (L and H["rsi4"] > 72) or (not L and H["rsi4"] < 28): add(-1, f"RSI 4H quá {'mua' if L else 'bán'} ({H['rsi4']:.0f})")
    if (L and H["hl"]) or (not L and H["lh"]): add(1, "cấu trúc 4H " + ("đáy cao dần" if L else "đỉnh thấp dần"))
    # 4) TradingView
    sup, res = [], []                                    # (giá, tên) vùng ủng hộ / cản
    sup += [(H["e34"], "EMA34 4H"), (H["e89"], "EMA89 4H"), (H["kijun"], "Kijun 4H")]
    if T:
        mine, oth = ("bull", "bear") if L else ("bear", "bull")
        for o in T.get("ob", []):
            edge = o["hi"] if o["side"] == "bull" else o["lo"]
            if o["side"] == mine and (p - edge) * sgn > 0: sup.append((edge, f"{'MUA' if L else 'BÁN'} OB {o['lo']:.4g}–{o['hi']:.4g}", o))
            if o["side"] == oth and (o["lo" if L else "hi"] - p) * sgn > -0.2 * A: res.append((o["lo"] if L else o["hi"], f"{'BÁN' if L else 'MUA'} OB {o['lo']:.4g}–{o['hi']:.4g}"))
        for f in T.get("fvg", []):
            if f["side"] == mine and (p - (f["hi"] if L else f["lo"])) * sgn > -0.2 * A:
                sup.append((f["hi"] if L else f["lo"], f"FVG {f['lo']:.4g}–{f['hi']:.4g}", f))
        bv = T.get("bb_v", {})
        if bv:
            sup += [(bv.get("VWAP L1U" if L else "VWAP U1U"), "VWAP L1" if L else "VWAP U1")]
            res += [(bv.get("VWAP U1U" if L else "VWAP L1U"), "VWAP U1" if L else "VWAP L1"), (bv.get("VWAP U2" if L else "VWAP L2"), "VWAP U2" if L else "VWAP L2")]
            reg = bv.get("EMA Regime")
            if reg and (p - reg) * sgn < 0: add(-1, f"giá sai phía EMA Regime BAMBAM ({reg:.4g})")
        vp = T.get("vp") or {}
        if vp.get("poc"):
            (sup if (p - vp["poc"]) * sgn > 0 else res).append((vp["poc"], "POC Swing VP"))
            for v in vp.get("va", []):
                (sup if (p - v) * sgn > 0 else res).append((v, "VAL/VAH Swing VP"))
        for lab in T.get("sd_lab", []):
            if "OTE" in lab["t"] and (("BUY" in lab["t"]) == L): sup.append((lab["y"], "OTE Sơn Dubai"))
            if "LIQ" in lab["t"] and (lab["y"] - p) * sgn > 0: res.append((lab["y"], "LIQ"))
            if "A+" in lab["t"]:
                add(1 if (("BUY" in lab["t"]) == L) else -1, f"{lab['t']} Sơn Dubai {lab['ago']} nến trước")
        flags = {**T.get("sd_flag", {}), **T.get("vp_flag", {})}
        for k, ago in flags.items():
            if "A+" in k: continue
            same = ("MUA" in k or "BUY" in k) == L
            add(1 if same else -1, f"cờ '{k}' {ago} nến trước")
        sdl = sorted([x for x in T.get("sd_lab", []) if x["t"] in ("BUY", "SELL") and x["ago"] >= 0], key=lambda x: x["ago"])
        if sdl:
            add(1 if (sdl[0]["t"] == "BUY") == L else -1, f"Sơn Dubai {sdl[0]['t']} gần nhất {sdl[0]['ago']} nến trước")
        for o in T.get("ob", []):
            if o["side"] == ("bear" if L else "bull") and o["lo"] <= p <= o["hi"]:
                add(-1, f"giá đang nằm TRONG {o['t'][:6]} {o['lo']:.4g}–{o['hi']:.4g}")
        bbl = sorted([x for x in T.get("bb_lab", []) if x["t"].startswith("◆")], key=lambda x: x["ago"])
        if bbl:                                          # chỉ tính nhãn ◆ gần nhất
            lab = bbl[0]; add(1 if (("BUY" in lab["t"]) == L) else -1, f"BAMBAM {lab['t']} gần nhất {lab['ago']} nến trước")
    else:
        r["warn"].append("không đọc được TradingView")
    res += [(H["hi30"] if L else H["lo30"], "đỉnh 30 nến 4H" if L else "đáy 30 nến 4H")]
    # 5) ENTRY CHỈ Ở OB KHUNG LỚN (EMA/Kijun chỉ để lọc xu hướng, không dùng làm điểm vào)
    mine = "bull" if L else "bear"
    def volm(t):
        import re
        m = re.search(r"Vol:\s*([\d.]+)([KMB]?)", t or "")
        return float(m.group(1)) * {"K": 1e3, "M": 1e6, "B": 1e9, "": 1}[m.group(2)] if m else 0
    obs = [o for o in (T or {}).get("ob", []) if o["side"] == mine
           and ((o["hi"] <= p + 0.2 * A and p - o["hi"] <= 4 * A) if L else (o["lo"] >= p - 0.2 * A and o["lo"] - p <= 4 * A))]
    if not obs:
        r["why"].append(f"không có {'MUA' if L else 'BÁN'} OB khung lớn (4H/{HTF_NAME}) trong 4 ATR → không có điểm vào"); r["grade"] = "CHỜ"; return r
    conf = [x for x in sup if x[0] and "EMA" not in x[1] and "Kijun" not in x[1] and "OB" not in x[1]]
    vmax = max(volm(o.get("t")) for o in obs) or 1
    def ob_score(o):
        inside = [x for x in conf if o["lo"] - 0.3 * A <= x[0] <= o["hi"] + 0.3 * A]
        return (2 if o.get("tf") == HTF_NAME else 1) + len(inside) + volm(o.get("t")) / vmax - abs(p - (o["hi"] if L else o["lo"])) / A * 0.3, inside
    ranked = sorted(((ob_score(o), o) for o in obs), key=lambda z: -z[0][0])
    (sc, inside), ob = ranked[0]
    e_hi, e_lo = (ob["hi"], ob["lo"]) if L else (ob["lo"], ob["hi"])
    entry = ob["hi"] - 0.3 * (ob["hi"] - ob["lo"]) if L else ob["lo"] + 0.3 * (ob["hi"] - ob["lo"])
    stop = (ob["lo"] - 0.3 * A) if L else (ob["hi"] + 0.3 * A)
    if abs(entry - stop) < 1.0 * A: stop = entry - sgn * 1.0 * A
    R = abs(entry - stop)
    cl = [(entry, f"{ob.get('tf', '')} {ob['t']} {ob['lo']:.4g}–{ob['hi']:.4g}")] + inside
    add(2 if ob.get("tf") == HTF_NAME else 1, f"entry tại {cl[0][1]}")
    if inside: add(1, "trong OB có thêm " + ", ".join(x[1] for x in inside))
    if (L and btc != "UP") or (not L and btc != "DN"):
        r["warn"].append(f"BTC 4H đang {btc} → KHÔNG đặt limit chờ sẵn; chỉ vào khi có nến 4H xác nhận tại OB")
    floor = max(0.8 * R, (p - entry) * sgn + 0.2 * A)   # TP phải vượt cả giá hiện tại
    tg = sorted({round(x[0], 10): x for x in res if x[0] and (x[0] - entry) * sgn >= floor}.values(), key=lambda x: x[0] * sgn)
    blockers = [x for x in res if x[0] and 0 < (x[0] - entry) * sgn < 0.8 * R and "OB" in x[1]]
    for b in blockers: add(-2, f"vật cản {b[1]} nằm ngay trên entry")
    tp1 = tg[0] if tg else (entry + sgn * 1.5 * R, "1.5R")
    tp2 = tg[1] if len(tg) > 1 else (entry + sgn * max(2.5 * R, abs(tp1[0] - entry) * 1.6), "mở rộng")
    rr1, rr2 = abs(tp1[0] - entry) / R, abs(tp2[0] - entry) / R
    if rr1 < 1.2: add(-1, f"RR1 thấp ({rr1:.1f})")
    r.update(entry_zone=(e_hi, e_lo), entry=entry, stop=stop, stop_pct=R / entry * 100, stop_atr=R / A,
             tp1=tp1[0], tp1_why=tp1[1], tp2=tp2[0], tp2_why=tp2[1], rr1=rr1, rr2=rr2,
             cluster=[x[1] for x in cl], dist_atr=abs(p - entry) / A)
    r["grade"] = "A" if r["score"] >= 8 else "B" if r["score"] >= 5 else "C"
    if (L and btc != "UP") or (not L and btc != "DN"):
        r["grade"] += "-chờ xác nhận"
    return r


def main():
    coins = [x.upper() for x in sys.argv[1:]] or WATCH
    print("now", datetime.now(timezone.utc).strftime("%d/%m %H:%M UTC"), "|", len(coins), "coin")
    b4 = kl("BTCUSDT", "4h", 150); cb = [x[4] for x in b4]
    btc = "UP" if ema(cb, 34) > ema(cb, 89) and cb[-1] > ema(cb, 89) else "DN" if ema(cb, 34) < ema(cb, 89) and cb[-1] < ema(cb, 89) else "MIX"
    print("BTC 4H:", btc, cb[-1])
    H = {}
    for c in coins:
        try: H[c] = htf(c + "USDT")
        except Exception as e: print("  bỏ", c, e)
    print("Đọc TradingView (chart sẽ tự đổi coin, xong sẽ trả lại)...")
    T = asyncio.run(read_tv(list(H)))
    R = [plan(c, H[c], T.get(c), btc) for c in H]
    json.dump(dict(time=datetime.now(timezone.utc).isoformat(), btc=btc, rows=R, tv=T), open(OUTDIR / "bambam_confluence.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)
    order = {"A": 0, "B": 1, "C": 2, "CHỜ": 3}
    R.sort(key=lambda r: (order.get((r.get("grade") or "Z")[:1] if "entry" in r else "CHỜ", 4), -r["score"]))
    md = [f"# BAMBAM × phân tích riêng — {datetime.now():%d/%m %H:%M} (BTC 4H {btc})", "",
          "| Hạng | Coin | Hướng | Điểm | Giá | Vùng vào | STL | TP1 / TP2 | RR | Cụm hỗ trợ |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in R:
        if "entry" in r:
            md.append(f"| {r['grade']} | {r['coin']} | {r['bias']} | {r['score']} | {r['p']:.5g} | {r['entry_zone'][0]:.5g}–{r['entry_zone'][1]:.5g} | "
                      f"{r['stop']:.5g} ({r['stop_pct']:.1f}%, {r['stop_atr']:.1f} ATR) | {r['tp1']:.5g} / {r['tp2']:.5g} | {r['rr1']:.1f}/{r['rr2']:.1f} | {', '.join(r['cluster'])} |")
    md += ["", "## Chi tiết"]
    for r in R:
        md.append(f"\n**{r['coin']}** {r['bias']} — điểm {r['score']} ({r.get('grade', '-')})")
        md += [f"- {w}" for w in r["why"] + r["warn"]]
        if "tp1" in r: md.append(f"- TP1 = {r['tp1_why']}, TP2 = {r['tp2_why']}")
    (OUTDIR / "bambam_confluence.md").write_text("\n".join(md), encoding="utf-8")
    print()
    for r in R:
        if "entry" in r:
            print(f"[{r['grade']}] {r['coin']:6} {r['bias']:5} điểm {r['score']:>2} | giá {r['p']:.5g} | vào {r['entry_zone'][0]:.5g}–{r['entry_zone'][1]:.5g} "
                  f"(cách {r['dist_atr']:.1f} ATR) | STL {r['stop']:.5g} ({r['stop_pct']:.1f}%) | TP {r['tp1']:.5g}/{r['tp2']:.5g} RR {r['rr1']:.1f}/{r['rr2']:.1f}")
            print("        + " + " ; ".join(r["why"]))
            if r["warn"]: print("        - " + " ; ".join(r["warn"]))
    print("\nĐứng ngoài/chờ:", ", ".join(f"{r['coin']}({r.get('grade', r['bias'])})" for r in R if "entry" not in r))
    print("Lưu:", (OUTDIR / "bambam_confluence.md").relative_to(HERE))


if __name__ == "__main__":
    main()
