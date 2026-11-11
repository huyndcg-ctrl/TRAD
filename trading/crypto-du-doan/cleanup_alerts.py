# Dọn alert CỦA CLAUDE (tag "· kịch bản DD/MM]" hoặc "· nhánh giảm DD/MM]", KHÔNG đụng "· home" hay alert khác):
#  1) kèo đã bị huỷ: alert ❌ của (coin, ngày) đã bắn (active=False) → xoá mọi alert của (coin, ngày) đó
#     ❌ "BỎ TẤT CẢ KÈO SHORT/LONG" đã bắn → xoá mọi alert cùng chiều của ngày đó
#  2) cũ hơn 3 ngày
#  3) trùng coin với kèo mới (truyền --replace BTC,ETH ... và --today DD/MM)
# Mặc định chỉ in ra (dry-run); thêm --apply để xoá thật.
import sys, asyncio, json, re, datetime, argparse; sys.path.insert(0, r'C:\Users\dell\Desktop\trad\crypto-du-doan')
import bambam_confluence as b
ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true'); ap.add_argument('--replace', default=''); ap.add_argument('--today', default='')
A = ap.parse_args()
TAG = re.compile(r'\[(\S+) [\d.,]+ · (?:kịch bản|nhánh giảm) (\d\d)/(\d\d)\]\s*$')
JS = """(async()=>{const r=await fetch('https://pricealerts.tradingview.com/%s',{method:'POST',credentials:'include',headers:{'Content-Type':'text/plain;charset=UTF-8'},body:JSON.stringify(%s)});return await r.text()})()"""
LIST = "(async()=>{const r=await fetch('https://pricealerts.tradingview.com/list_alerts',{credentials:'include'});return await r.text()})()"
def side(m):
    return 'short' if 'SHORT' in m else 'long' if ('LONG' in m or 'BUY' in m) else '?'
async def main():
    now = datetime.datetime.now()
    rep = {x.strip().upper() for x in A.replace.split(',') if x.strip()}
    async with b.CDP() as c:
        assert not await c.ev("document.body.innerText.includes('Phiên bị ngắt kết nối')"), 'Phiên bị ngắt kết nối'
        L = json.loads(await c.ev(LIST))['r']
        mine = []
        for a in L:
            m = TAG.search(a['message'].strip())
            if m: mine.append((a, m.group(1), f'{m.group(2)}/{m.group(3)}', int(m.group(2)), int(m.group(3))))
        dead, dead_all = set(), set()
        for a, coin, d, *_ in mine:
            if a['message'].startswith('❌') and not a.get('active'):
                if 'TẤT CẢ' in a['message']: dead_all.add((d, side(a['message'])))
                else: dead.add((coin, d))
        out = []
        for a, coin, d, dd, mm in mine:
            age = (now - datetime.datetime(now.year if mm <= now.month else now.year - 1, mm, dd)).days
            why = ('❌ đã bắn' if (coin, d) in dead else
                   '❌ chung đã bắn' if (d, side(a['message'])) in dead_all or (d, '?') in dead_all else
                   f'cũ {age} ngày' if age > 3 else
                   'trùng coin kèo mới' if coin in rep and d != A.today else None)
            if why: out.append(a['alert_id']); print('XOÁ', a['alert_id'], coin, d, why, '|', a['message'][:60])
        print(len(out), 'alert sẽ xoá' if not A.apply else 'alert xoá')
        if A.apply and out:
            print(await c.ev(JS % ('delete_alerts', json.dumps({'payload': {'alert_ids': out}}))))
            L = json.loads(await c.ev(LIST))['r']
            print('còn lại', len(L), '| sót:', [a['alert_id'] for a in L if a['alert_id'] in out])
asyncio.run(main())
