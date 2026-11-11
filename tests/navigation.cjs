// Optional UI regression: npm install playwright, then node tests/navigation.cjs.
// Start app.py first; TEST_URL and TEST_PASSWORD override the local test login.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.TEST_URL||'http://127.0.0.1:5055');
 await page.locator('#email').fill('admin@petshop.com');
 await page.locator('#password').fill(process.env.TEST_PASSWORD||'NavigationTest123');
 await page.locator('#login button').click();await page.locator('nav').waitFor();
 for(const area of ['clinic','petshop','clinic','petshop']){
  await page.locator(`.area-switch button[data-area="${area}"]`).click();
  const keys=await page.locator('nav button').evaluateAll(bs=>bs.map(b=>b.dataset.nav));
  for(const key of keys){
   await page.locator(`nav button[data-nav="${key}"]`).click();
   assert.equal(await page.locator('nav button.active').getAttribute('data-nav'),key);
   assert.equal(await page.locator('body').getAttribute('data-area'),area);
   if(key!=='dashboard'){
    if(await page.locator('#new').count()){
     await page.locator('#new').click();await page.locator('dialog[open]').waitFor();
     await page.locator('#close').click();assert.equal(await page.locator('dialog[open]').count(),0);
     assert.equal(await page.locator('nav button.active').getAttribute('data-nav'),key);
    }
   }
  }
 }
 await page.setViewportSize({width:390,height:844});
 await page.locator('.area-switch button[data-area="clinic"]').click();
 await page.locator('nav button[data-nav="records"]').click();
 assert.equal(await page.locator('nav button.active').getAttribute('data-nav'),'records');
 await page.locator('#logout').click();await page.locator('#login').waitFor();
 assert.deepEqual(errors,[]);console.log('PASS: all navigation items, area switches, dialogs, mobile and logout.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
