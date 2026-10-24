// Theme toggle only: auto (system) -> light -> dark. The choice is kept in localStorage ('awi-theme').
function theme(){const b=document.querySelector('[data-theme-toggle]');if(!b)return;const order=['auto','light','dark'],lab={auto:'Theme: match system',light:'Theme: light',dark:'Theme: dark'};
  const cur=()=>document.documentElement.getAttribute('data-theme')||'auto';
  const paint=m=>{b.dataset.mode=m;b.setAttribute('aria-label',lab[m]+' (change)');b.title=lab[m]};paint(cur());
  b.addEventListener('click',()=>{const n=order[(order.indexOf(cur())+1)%3];if(n==='auto')document.documentElement.removeAttribute('data-theme');else document.documentElement.setAttribute('data-theme',n);
    try{n==='auto'?localStorage.removeItem('awi-theme'):localStorage.setItem('awi-theme',n)}catch{}paint(n)})}
theme();
