const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const SRC=fs.readFileSync(path.join(__dirname,'..','src','app.js'),'utf8');
function dom(gen){
  const note={dataset:{generated:gen},textContent:''},dot={cls:new Set(),classList:{add(c){dot.cls.add(c)}}};
  const panels={},tabs=['search','scrape','browser'].map((t,i)=>{panels['panel-'+t]={hidden:false};const l={};return{dataset:{tab:t},attrs:{'aria-controls':'panel-'+t},tabIndex:i?-1:0,
    getAttribute(k){return this.attrs[k]},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,f){l[k]=f},fire(k,e){l[k](e)},focus(){ctx.focused=this}}});
  const root={querySelectorAll:()=>tabs};
  const ctx={console,Date,isNaN,location:{hash:''},history:{replaceState(){}},localStorage:{getItem:()=>null},
    fetch:async()=>({ok:false}),
    document:{documentElement:{getAttribute:()=>null},getElementById:id=>panels[id]||null,
      querySelector:s=>s==='[data-tabs]'?root:null,
      querySelectorAll:s=>s==='[data-stale-note]'?[note]:s==='[data-fresh-dot]'?[dot]:[]}};
  vm.createContext(ctx);vm.runInContext(SRC,ctx);return{ctx,note,dot,tabs,panels};
}
const day=864e5,g='2026-10-19T20:39:05+00:00',t0=Date.parse(g);let n=0;
const ok=(name,f)=>{f();n++;console.log('ok',name)};
ok('fresh result is not stale',()=>{const d=dom(g);assert.strictEqual(JSON.stringify(d.ctx.stale(t0+3*day)),JSON.stringify([]));assert.strictEqual(d.note.textContent,'')});
ok('old result is marked stale',()=>{const d=dom(g);assert.strictEqual(JSON.stringify(d.ctx.stale(t0+12*day)),JSON.stringify([12]));assert.match(d.note.textContent,/stale: results are 12 days old/);assert(d.dot.cls.has('fresh-dot--stale'))});
ok('stale boundary is 10 days',()=>{const d=dom(g);assert.strictEqual(JSON.stringify(d.ctx.stale(t0+10*day+1)),JSON.stringify([]))});
ok('tabs hide other panels on load',()=>{const d=dom(g);assert.strictEqual(d.panels['panel-search'].hidden,false);assert.strictEqual(d.panels['panel-scrape'].hidden,true)});
ok('arrow keys move selection',()=>{const d=dom(g);d.tabs[0].fire('keydown',{key:'ArrowRight',preventDefault(){}});assert.strictEqual(d.tabs[1].attrs['aria-selected'],'true');assert.strictEqual(d.tabs[1].tabIndex,0);assert.strictEqual(d.tabs[0].tabIndex,-1);assert.strictEqual(d.panels['panel-scrape'].hidden,false);assert.strictEqual(d.ctx.focused,d.tabs[1])});
ok('End and Home keys',()=>{const d=dom(g);d.tabs[0].fire('keydown',{key:'End',preventDefault(){}});assert.strictEqual(d.tabs[2].attrs['aria-selected'],'true');d.tabs[2].fire('keydown',{key:'Home',preventDefault(){}});assert.strictEqual(d.tabs[0].attrs['aria-selected'],'true')});
console.log(`JS smoke: ${n} passed`);
