const NODATA='<p class="nodata">No data yet.</p>';
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function j(u){try{const r=await fetch(u,{cache:'no-store'});return r.ok?await r.json():null}catch{return null}}
const STALE_AFTER_DAYS=10;
function theme(){const b=document.querySelector('[data-theme-toggle]');if(!b)return;const order=['auto','light','dark'],lab={auto:'Theme: match system',light:'Theme: light',dark:'Theme: dark'};
  const cur=()=>document.documentElement.getAttribute('data-theme')||'auto';
  const paint=m=>{b.dataset.mode=m;b.setAttribute('aria-label',lab[m]+' (change)');b.title=lab[m]};paint(cur());
  b.addEventListener('click',()=>{const n=order[(order.indexOf(cur())+1)%3];if(n==='auto')document.documentElement.removeAttribute('data-theme');else document.documentElement.setAttribute('data-theme',n);
    try{n==='auto'?localStorage.removeItem('awi-theme'):localStorage.setItem('awi-theme',n)}catch{}paint(n)})}
function tabs(){const root=document.querySelector('[data-tabs]');if(!root)return;const ts=[...root.querySelectorAll('[role="tab"]')];
  const sel=(t,focus)=>{ts.forEach(x=>{const on=x===t;x.setAttribute('aria-selected',on?'true':'false');x.tabIndex=on?0:-1;const p=document.getElementById(x.getAttribute('aria-controls'));if(p)p.hidden=!on});
    if(focus)t.focus();if(history.replaceState)history.replaceState(null,'','#'+t.dataset.tab)};
  ts.forEach((t,i)=>{t.addEventListener('click',()=>sel(t));t.addEventListener('keydown',ev=>{let j=null;
    if(ev.key==='ArrowRight')j=(i+1)%ts.length;else if(ev.key==='ArrowLeft')j=(i-1+ts.length)%ts.length;else if(ev.key==='Home')j=0;else if(ev.key==='End')j=ts.length-1;
    if(j!=null){ev.preventDefault();sel(ts[j],true)}})});
  const h=location.hash.slice(1),first=ts.find(t=>t.dataset.tab===h);
  ts.forEach(t=>{const p=document.getElementById(t.getAttribute('aria-controls'));if(p)p.hidden=t!==(first||ts[0])});
  if(first)sel(first)}
function stale(now){const out=[];document.querySelectorAll('[data-stale-note]').forEach(el=>{const g=Date.parse(el.dataset.generated);if(isNaN(g))return;
  const days=Math.floor(((now||Date.now())-g)/864e5);if(days>STALE_AFTER_DAYS){el.textContent=` · stale: results are ${days} days old`;out.push(days);
    document.querySelectorAll('[data-fresh-dot]').forEach(d=>d.classList.add('fresh-dot--stale'))}});return out}
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
theme();tabs();stale();prices();
