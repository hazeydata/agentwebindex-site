const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const SRC=fs.readFileSync(path.join(__dirname,'..','src','app.js'),'utf8');
const real=JSON.parse(fs.readFileSync(path.join(__dirname,'..','data','benchmarks','latest.json'),'utf8'));
function el(){return{innerHTML:'',classList:{add(){},remove(){}},dataset:{}}}
async function run(name,data,check,only){
  const board=el(),tabs=['search','scrape','browser'].map(t=>Object.assign(el(),{dataset:{tab:t}}));
  const errs=[];
  const ctx={console,document:{getElementById:id=>id==='board'?board:null,querySelectorAll:()=>tabs},
    fetch:async()=>({ok:data!==null,json:async()=>data})};
  vm.createContext(ctx);
  process.removeAllListeners('unhandledRejection');process.on('unhandledRejection',e=>errs.push(e));
  vm.runInContext(SRC,ctx);
  await new Promise(r=>setTimeout(r,20));
  for(const t of tabs)if(!only||t.dataset.tab===only)t.onclick&&t.onclick();
  await new Promise(r=>setTimeout(r,5));
  assert.deepStrictEqual(errs.map(String),[],name);
  check(board.innerHTML);console.log('ok',name);
}
(async()=>{
  await run('status with skips+flags (current data)',Object.assign({},real,{flags:[{set:'news_2026-W42',flag:'thin'}]}),h=>{assert(h.includes('Run status'));assert(h.includes('<table>'));assert((h.match(/Run status/g)||[]).length===1)});
  await run('status without skips',Object.assign({},real,{skips:[],flags:[],has_results:false,not_run_yet:[]}),h=>{assert(!h.includes('Run status'));assert(h.includes('No data yet'))});
  await run('no data file',null,h=>{assert(h.includes('No data yet'));assert(!h.includes('Run status'))});
  await run('results present',{has_results:true,generated_at:'x',skips:[{scope:'set',set:'s',status:'k',reason:'r'}],flags:[],freshness:[],tables:{search:[{provider:'p',set:'s',mock:false,attempted:{v:2},success_rate:{v:.5},skipped_tos:{count:0},p50_latency_ms:{v:10}}],scrape:[],browser:[]}},h=>{assert(h.includes('Run status'))});
  // last clicked tab (browser) is what the harness inspects, so the row is in browser too
  await run('rate-limited + not run yet',{has_results:true,generated_at:'x',skips:[],flags:[],freshness:[],not_run_yet:[{provider:'apify',categories:['scrape']}],tables:{search:[{provider:'firecrawl',set:'s',mock:false,attempted:{v:10},success_rate:{v:.5},answered_display:'5/10 answered + 6 rate-limited (free tier)',rate_limited:{v:6,label:'rate-limited (free tier)',note:'free-tier rate limit is the cause'},skipped_tos:{count:0},p50_latency_ms:{v:10}}],scrape:[],browser:[{provider:'firecrawl',set:'s',mock:false,attempted:{v:10},success_rate:{v:.5},answered_display:'5/10 answered + 6 rate-limited (free tier)',rate_limited:{v:6,label:'rate-limited (free tier)',note:'free-tier rate limit is the cause'},skipped_tos:{count:0},p50_latency_ms:{v:10}}]}},h=>{assert(h.includes('5/10 answered'));assert(h.includes('6 rate-limited (free tier)'));assert(h.includes('free-tier rate limit'));assert(h.includes('apify (scrape): not run yet'))});
  await run('real run-1 data, search tab',real,h=>{assert(h.includes('below minimum (n=16)'));assert(h.includes('6 rate-limited (free tier)'));assert(h.includes('5/10 answered'));assert(h.includes('Run date'));assert(h.includes('2026-10-15'));assert(!h.includes('>brave<'));assert(h.includes('brightdata (scrape): not run yet'))},'search');
  await run('real data, browser tab',real,h=>{assert(h.includes('browserless'));assert(h.includes('newsfetch_2026-42'));assert(h.includes('below minimum (n=16)'))},'browser');
  console.log('JS smoke: 7 passed');
})().catch(e=>{console.error('JS smoke FAILED:',e.message);process.exit(1)});
