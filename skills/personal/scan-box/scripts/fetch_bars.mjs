import { chart, data } from 'file:///C:/Users/dell/tradingview-mcp/src/core/index.js';
import fs from 'fs';
import path from 'path';

const OUT = process.argv[2];
const TF = process.argv[3] || '60';
const COUNT = Number(process.argv[4] || 300);
const syms = process.argv.slice(5);
fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const norm = s => String(s || '').toUpperCase().replace(/^.*:/, '');

const st0 = await chart.getState();
if (String(st0.resolution) !== TF) await chart.setTimeframe({ timeframe: TF });

for (const sym of syms) {
  let ok = false;
  for (let attempt = 0; attempt < 3 && !ok; attempt++) {
    try {
      await chart.setSymbol({ symbol: sym });
      await sleep(1500);
      let st = await chart.getState();
      if (String(st.resolution) !== TF) { await chart.setTimeframe({ timeframe: TF }); await sleep(1500); st = await chart.getState(); }
      if (norm(st.symbol) !== norm(sym)) { console.log(`MISMATCH ${sym} got ${st.symbol}`); continue; }
      let r = await data.getOhlcv({ count: COUNT });
      await sleep(500);
      const r2 = await data.getOhlcv({ count: COUNT });
      const stAfter = await chart.getState();
      if (norm(stAfter.symbol) !== norm(sym) || String(stAfter.resolution) !== TF) { console.log(`CHANGED during ${sym}: ${stAfter.symbol} ${stAfter.resolution}`); continue; }
      r = r2;
      const bars = r.bars;
      const dt = bars.length > 1 ? bars[bars.length - 1].time - bars[bars.length - 2].time : 0;
      fs.writeFileSync(path.join(OUT, sym.replace(/[:.]/g, '_') + '.json'), JSON.stringify({ symbol: st.symbol, req: sym, tf: TF, bars }));
      console.log(`OK ${sym} -> ${st.symbol} bars=${bars.length} dt=${dt} last=${new Date(bars[bars.length-1].time*1000).toISOString()} close=${bars[bars.length-1].close}`);
      ok = true;
    } catch (e) { console.log(`ERR ${sym} ${e.message}`); await sleep(1500); }
  }
  if (!ok) console.log(`FAIL ${sym}`);
}
process.exit(0);
