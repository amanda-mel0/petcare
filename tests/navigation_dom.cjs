// Optional regression test: npm install jsdom; node tests/navigation_dom.cjs
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');
const fixture={user:{name:'Admin',role:'admin'},csrf:'token',tutors:[],pets:[],professionals:[],services:[],appointments:[],records:[],products:[],orders:[],stock_movements:[],users:[]};
async function verify(code){
 const dom=new JSDOM(fs.readFileSync(path.join(root,'static/index.html'),'utf8'),{runScripts:'outside-only',url:'http://localhost'});
 const w=dom.window;w.fetch=async()=>({ok:true,json:async()=>fixture});w.confirm=()=>true;
 w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
 const errors=[];w.addEventListener('error',e=>errors.push(e.error));w.eval(code);
 await new Promise(r=>setImmediate(r));
 for(const area of ['clinic','petshop','clinic','petshop']){
  w.document.querySelector(`.area-switch button[data-area="${area}"]`).click();
  const keys=Array.from(w.document.querySelectorAll('nav button'),b=>b.dataset.nav);
  for(const key of keys){
   w.document.querySelector(`nav button[data-nav="${key}"]`).click();
   assert.equal(w.document.querySelector('nav button.active').dataset.nav,key,`${area}: ${key}`);
   assert.equal(w.document.body.dataset.area,area);
   const button=w.document.querySelector('#new');
   if(button){button.click();assert(w.document.querySelector('dialog[open]'));w.document.querySelector('#close').click();assert(!w.document.querySelector('dialog[open]'));assert.equal(w.document.querySelector('nav button.active').dataset.nav,key);}
  }
 }
 assert.deepEqual(errors,[]);dom.window.close();
}
(async()=>{
 const code=fs.readFileSync(path.join(root,'static/app.js'),'utf8');
 if(process.env.CHECK_OLD_BUG){
  await assert.rejects(()=>verify(code.replace(".area-switch button[data-area]","[data-area]")),/clinic: appointments/);
  console.log('Original navigation bug reproduced.');
 }
 await verify(code);console.log('PASS: menu clicks, bubbling, dialogs and repeated area switches.');
})().catch(e=>{console.error(e);process.exitCode=1});
