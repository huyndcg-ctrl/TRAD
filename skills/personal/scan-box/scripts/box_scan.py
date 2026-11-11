"""Quét mô hình box 1H: hộp tích luỹ -> quét thanh khoản dưới đáy -> phá cạnh trên -> retest cạnh trên.

Cách dùng:  python box_scan.py <thư_mục_nến_mới> [<thư_mục_nến_cũ>]
Mỗi file JSON trong thư mục do fetch_bars.mjs ghi ra: {symbol, req, tf, bars:[{time,open,high,low,close,volume}]}.
Nến cuối luôn bị bỏ (đang chạy) — chỉ dùng nến đã đóng.
"""
import json, sys, os, datetime
import numpy as np

MINL, MAXL = 48, 240      # độ dài hộp: 2–10 ngày nến 1H
MAXR = 0.15               # biên độ hộp tối đa 15%
VN = datetime.timezone(datetime.timedelta(hours=7))


def vn(t):
    return datetime.datetime.fromtimestamp(int(t), VN).strftime('%d/%m %Hh')


def load(bars):
    bars = bars[:-1]  # bỏ nến đang chạy
    f = lambda k: np.array([b[k] for b in bars])
    return f('time'), f('high'), f('low'), f('close'), f('volume')


def is_box(h, c, s, e):
    cs = c[s:e+1]
    bot = np.percentile(cs, 5); top = np.percentile(h[s:e+1], 95)
    if top <= bot or top / bot - 1 > MAXR: return None
    if np.mean((cs >= bot * 0.985) & (cs <= top * 1.003)) < 0.9: return None   # ≥90% close nằm trong hộp
    if abs(np.polyfit(np.arange(len(cs)), cs, 1)[0] * len(cs)) > 0.6 * (top - bot): return None  # đi ngang, không phải kênh dốc
    return bot, top


def find_sweep(t, l, c, s, e, bot):
    """Râu thủng đáy ≥1% rồi có nến đóng lại trên đáy trong ≤6 nến."""
    sw = None
    for i in range(s + 3, e + 1):
        if l[i] >= bot * 0.99: continue
        back = next((k - i for k in range(i, min(i + 7, e + 1)) if c[k] > bot), None)
        if back is None: continue
        d = (bot - l[i]) / bot * 100
        if sw is None or d > sw['depth'] or (t[i] > sw['ts'] and d >= 1):
            sw = dict(t=vn(t[i]), ts=t[i], depth=d, back=back, low=l[i])
    return sw


def plan(top, bot, price):
    H = top - bot; mid = (top + bot) / 2
    sl = max(mid, top - 0.4 * H); tp = top + H
    return dict(entry=top, sl=sl, tp=tp, rr=(tp - top) / (top - sl),
                rr_now=(tp - price) / (price - sl) if price > sl else None)


def current_box(bars):
    """Hộp hiện tại (giá vẫn trong hộp), hoặc hộp gần nhất trong 48 nến qua."""
    t, h, l, c, v = load(bars); n = len(c)
    for lag in range(0, 49):
        e = n - 1 - lag; best = None
        for L in range(MINL, MAXL + 1):
            s = e - L + 1
            if s < 0: break
            bx = is_box(h, c, s, e)
            if bx and bx[0] * 0.985 <= c[e] <= bx[1] * 1.003: best = (s, *bx)
        if best: break
    if not best: return None
    s, bot, top = best; p = c[-1]; H = top - bot
    st = 'THUNG_DAY' if p < bot * 0.985 else 'TREN_CANH_TREN' if p > top * 1.003 else 'TRONG_HOP'
    return dict(price=p, bot=bot, top=top, days=(e - s + 1) / 24, frm=vn(t[s]), st=st,
                dist=(p / top - 1) * 100, pos=(p - bot) / H * 100, sweep=find_sweep(t, l, c, s, n - 1, bot), last=vn(t[-1]))


def breakout_retest(bars):
    """Hộp đã có sweep + đã phá cạnh trên (hoặc đang chờ phá). Trạng thái A = đang retest cạnh trên."""
    t, h, l, c, v = load(bars); n = len(c); best = None
    for s in range(24, n - MINL, 2):
        for e in range(s + MINL - 1, min(s + MAXL, n)):
            bx = is_box(h, c, s, e)
            if not bx: continue
            bot, top = bx
            if np.sum(c[s:e+1] > top * 1.01) > 2: continue          # không có close mạnh trên đỉnh trong hộp
            if h[max(0, s-72):s].max() < top * 1.03: continue        # giá đến từ trên xuống (có đợt giảm trước hộp)
            last = e == n - 1
            if not last and not c[e+1] > top * 1.002: continue       # nến kế tiếp phải close phá đỉnh
            sw = find_sweep(t, l, c, s, e, bot)
            if not sw: continue
            score = (e - s + 1) + (0 if last else 30)
            if best is None or score > best['score'] or (score == best['score'] and e > best['e']):
                best = dict(s=s, e=e, bot=bot, top=top, sw=sw, brk=None if last else e + 1, score=score)
    if not best: return None
    s, e, bot, top = best['s'], best['e'], best['bot'], best['top']
    p = c[-1]; mid = (top + bot) / 2; d = (p / top - 1) * 100
    r = dict(bot=bot, top=top, days=(e - s + 1) / 24, sweep=best['sw'], dist=d, **plan(top, bot, p))
    if best['brk'] is None:
        r['state'] = 'C'                                              # đã sweep, chờ phá cạnh trên
    else:
        b = best['brk']
        r.update(brk=vn(t[b]), brk_age=n - 1 - b, brk_vol=v[b] / v[s:e+1].mean())
        r['state'] = 'FAIL' if p < mid else 'WEAK' if d < -2 else 'A' if d <= 2 else 'B' if d <= 8 else 'D'
    return r


def run(D):
    out = {}
    for f in sorted(os.listdir(D)):
        j = json.load(open(os.path.join(D, f), encoding='utf-8'))
        out[j['req']] = (current_box(j['bars']), breakout_retest(j['bars']))
    return out


def fmt(x):
    return '%.6g' % x


if __name__ == '__main__':
    new = run(sys.argv[1]); old = run(sys.argv[2]) if len(sys.argv) > 2 else {}
    first = next((v[0] for v in new.values() if v[0]), None)
    print('NEN DONG CUOI:', first['last'] if first else '?')
    print('\n=== RETEST / BREAKOUT (state A tot nhat; B da chay xa; C chua pha; WEAK/FAIL bo) ===')
    for k, (_, r) in sorted(new.items(), key=lambda kv: (kv[1][1] or {}).get('state', '~')):
        if not r or r['state'] in ('FAIL',): continue
        if r['state'] != 'C' and r['brk_age'] > 72: continue
        sw = r['sweep']
        print('%-5s %-22s box %s/%s %.1fd | sweep %s -%.1f%% | brk %s vol %.1fx | dist %.1f%% | E %s SL %s TP %s RR %.1f rr_now %s' % (
            r['state'], k, fmt(r['bot']), fmt(r['top']), r['days'], sw['t'], sw['depth'], r.get('brk', '-'),
            r.get('brk_vol', 0), r['dist'], fmt(r['entry']), fmt(r['sl']), fmt(r['tp']), r['rr'],
            '%.1f' % r['rr_now'] if r['rr_now'] else '-'))
    print('\n=== HOP HIEN TAI (sap theo vi tri trong hop, cao -> thap) ===')
    for k, (b, _) in sorted(((k, v) for k, v in new.items() if v[0]), key=lambda kv: -kv[1][0]['pos']):
        sw = b['sweep']; ch = ''
        o = (old.get(k) or (None,))[0]
        if o:
            if o['st'] != b['st']: ch += ' DOI:%s->%s' % (o['st'], b['st'])
            if sw and (not o['sweep'] or sw['t'] != o['sweep']['t']): ch += ' SWEEP_MOI'
        print('%-14s %-22s p=%s day=%s dinh=%s %.1fd tu %s | sweep %s | cach dinh %.1f%% | vi tri %.0f%%%s' % (
            b['st'], k, fmt(b['price']), fmt(b['bot']), fmt(b['top']), b['days'], b['frm'],
            'chua' if not sw else '%s -%.1f%%' % (sw['t'], sw['depth']), b['dist'], b['pos'], ch))
    print('\nKHONG CO HOP:', [k for k, v in new.items() if not v[0]])
