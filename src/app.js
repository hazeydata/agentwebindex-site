const NODATA='<p class="nodata">No data yet.</p>';
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function j(u){try{const r=await fetch(u,{cache:'no-store'});return r.ok?await r.json():null}catch{return null}}
async function board(){
  const el=document.getElementById('board');if(!el)return;
  const d=await j('/data/benchmarks/latest.json');
  const c=x=>x&&x.v!=null?x:null;
  const pct=x=>c(x)?(x.v*100).toFixed(1)+'%':'n/a';
  const money=x=>x&&x.v==null&&x.na_reason?`<span class="muted">${esc(x.na_reason)}</span>`:x&&x.display?esc(x.display)+(x.lower_bound?` <span class="flag" title="${esc(x.lower_bound_reason)}">lower bound</span>`:'')+(x.tier?` <span class="muted">(${esc(x.tier)})</span>`:''):'n/a';
  const status=()=>{if(!d)return'';const sk=d.skips||[],fl=d.flags||[];if(!sk.length&&!fl.length)return'';
    return `<h3>Run status ${esc(d.run_date||'')}</h3>`+(fl.length?'<ul>'+fl.map(f=>`<li class="flag">${esc(f.set)}: ${esc(f.flag)}</li>`).join('')+'</ul>':'')+
      (sk.length?'<table><tr><th>Skipped</th><th>Status</th><th>Reason</th></tr>'+sk.map(k=>`<tr><td>${esc(k.set||[k.provider,k.category].filter(Boolean).join(' / ')||k.scope)}</td><td>${esc(k.status)}</td><td class="muted">${esc(k.reason)}</td></tr>`).join('')+'</table>':'')+status()};
  const fb=r=>(r.flags||[]).map(f=>` <span class="flag">${esc(f)}</span>`).join('');
  const draw=cat=>{
    const rows=(d&&d.has_results&&d.tables?d.tables[cat]:[]).filter(r=>!r.mock&&c(r.attempted));
    if(!rows.length){el.innerHTML=NODATA.replace('yet.',`yet for ${cat}.`)+(d?`<p class="muted">Last run ${esc(d.generated_at)}: no provider produced results.</p>`+status():'');return}
    rows.sort((a,b)=>b.success_rate.v-a.success_rate.v);
    el.innerHTML=`<p class="muted">Generated ${esc(d.generated_at)} from run logs. Free tier is a note, never a cost.</p><table><tr><th>Provider</th><th>Set</th><th>Success</th><th>n</th><th>ToS-skipped</th><th>p50 ms</th><th>Entry tier $/1k</th><th>Entry $/1k successful</th><th>Volume tier $/1k</th><th>Volume $/1k successful</th><th>Free quota</th></tr>`+
      rows.map(r=>`<tr><td>${esc(r.provider)}</td><td>${esc(r.set)}${fb(r)}</td><td>${pct(r.success_rate)}</td><td>${r.attempted.v}</td><td>${r.skipped_tos.count}</td><td>${c(r.p50_latency_ms)?r.p50_latency_ms.v.toFixed(0):'n/a'}</td><td>${money(r.entry_tier_cost_per_1k)}</td><td>${money(r.entry_tier_cost_per_successful_1k)}</td><td>${money(r.volume_tier_cost_per_1k)}</td><td>${money(r.volume_tier_cost_per_successful_1k)}</td><td class="muted">${esc(r.free_quota_note)}</td></tr>`).join('')+'</table>'+
      (cat==='search'&&d.freshness&&d.freshness.length?'<h3>Freshness (weekly news set)</h3><table><tr><th>Provider</th><th>Week</th><th>n</th><th>fresh_hit@10</th><th>median lag h</th><th>censored</th><th>set sha</th></tr>'+d.freshness.map(f=>`<tr><td>${esc(f.provider)}</td><td>${esc(f.week)}${fb(f)}</td><td>${f.n}</td><td>${pct(f.fresh_hit_at_10)}</td><td>${c(f.median_lag_h)?f.median_lag_h.v.toFixed(1):'n/a'}</td><td>${pct(f.censored_share)}</td><td class="muted">${esc((f.set_sha||'').slice(0,12))}</td></tr>`).join('')+'</table>':'')+status()};
  document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');draw(b.dataset.tab)});
  draw('search');
}
async function prices(){
  const el=document.getElementById('prices');if(!el)return;
  const idx=await j('/data/prices/index.json');
  if(!idx||!idx.providers||!idx.providers.length){el.innerHTML=NODATA;return}
  let h=`<p class="muted">Last snapshot ${esc(idx.generated_at)}</p><table><tr><th>Provider</th><th>Status</th><th>Amounts on page</th><th>Changed vs previous</th></tr>`;
  for(const p of idx.providers){const s=await j(`/data/prices/${p.provider}.json`)||{};
    const amts=(s.prices_found||[]);
    h+=`<tr><td><a href="${esc(s.url)}">${esc(s.name||p.provider)}</a></td><td class="${p.status==='ok'?'':'err'}">${esc(p.status)}${s.error?': '+esc(s.error):''}</td><td>${amts.length?esc(amts.slice(0,12).join(', '))+(amts.length>12?` … (+${amts.length-12})`:''):'<span class="muted">no data yet</span>'}</td><td>${s.diff&&s.diff.changed!=null?(s.diff.changed?'yes':'no'):'<span class="muted">first snapshot</span>'}</td></tr>`}
  el.innerHTML=h+'</table>';
}
board();prices();
