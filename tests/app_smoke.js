const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const SRC=fs.readFileSync(path.join(__dirname,'..','src','app.js'),'utf8');
function dom(initial){
  const attrs={};if(initial)attrs['data-theme']=initial;const store={};let click;
  const btn={dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,f){click=f}};
  const ctx={console,localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=v},removeItem:k=>{delete store[k]}},
    document:{documentElement:{getAttribute:k=>attrs[k]??null,setAttribute:(k,v)=>{attrs[k]=v},removeAttribute:k=>{delete attrs[k]}},
      querySelector:s=>s==='[data-theme-toggle]'?btn:null}};
  vm.createContext(ctx);vm.runInContext(SRC,ctx);return{btn,attrs,store,click:()=>click()};
}
let n=0;const ok=(name,f)=>{f();n++;console.log('ok',name)};
ok('starts in auto',()=>{const d=dom();assert.strictEqual(d.btn.dataset.mode,'auto')});
ok('click cycles auto -> light -> dark -> auto',()=>{const d=dom();d.click();assert.strictEqual(d.attrs['data-theme'],'light');assert.strictEqual(d.store['awi-theme'],'light');
  d.click();assert.strictEqual(d.attrs['data-theme'],'dark');d.click();assert.strictEqual(d.attrs['data-theme'],undefined);assert.strictEqual(d.store['awi-theme'],undefined)});
ok('saved theme is shown on the button',()=>{const d=dom('dark');assert.strictEqual(d.btn.dataset.mode,'dark')});
ok('script makes no network calls',()=>{assert(!/fetch|XMLHttpRequest/.test(SRC))});
console.log(`JS smoke: ${n} passed`);
