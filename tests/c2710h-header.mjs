import { createRequire } from 'node:module';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import assert from 'node:assert/strict';
const require = createRequire(process.env.C2710H_PLAYWRIGHT || import.meta.url);
const { chromium } = require('@playwright/test');
const root = resolve('static');
const out = process.env.C2710H_EVIDENCE || 'test-results/c2710h';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const report=[];
for(const [width,height] of [[1920,1080],[1440,900],[1366,786]].filter(([w])=>!process.env.C2710H_WIDTH || w===Number(process.env.C2710H_WIDTH))) {
 const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
 const errors=[];const served=new Set(); page.on('pageerror',e=>errors.push(String(e)));
 await page.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());
  if(!['GET','HEAD'].includes(req.method()))return route.abort();
  if(u.origin==='http://127.0.0.1:8159'&&(u.pathname==='/'||u.pathname.startsWith('/js/')||u.pathname.startsWith('/css/'))) {
   const rel=u.pathname==='/'?'/index.html':u.pathname;
   try {const body=await readFile(root+rel);served.add(rel);if(rel==='/js/main.js')await new Promise(r=>setTimeout(r,800));return route.fulfill({status:200,body,contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html'})[extname(rel)]});}catch{}
  }
  return route.continue();
 });
 await page.addInitScript(()=>{window.__headerFrames=[];function sample(){const f=document.querySelector('#job-form'),p=document.querySelector('#nowPlayingPanel');if(f){const a=f.getBoundingClientRect(),b=p.getBoundingClientRect();window.__headerFrames.push({t:performance.now(),x:a.x,y:a.y,w:a.width,h:a.height,cardX:b.x,cardY:b.y,cardH:b.height});}if(performance.now()<3500)requestAnimationFrame(sample);}requestAnimationFrame(sample)});
 for(const scenario of ['cold','reload','forced','warm']) {
  if(scenario==='cold'||scenario==='warm')await page.goto('http://127.0.0.1:8159/',{waitUntil:'commit'});
  else if(scenario==='forced'){const cdp=await page.context().newCDPSession(page);await cdp.send('Network.clearBrowserCache');await page.reload({waitUntil:'commit'});await cdp.detach();}
  else await page.reload({waitUntil:'commit'});
  await page.locator('#job-form').waitFor({state:'attached'}); await page.screenshot({path:`${out}/${width}-${scenario}-initial.png`}); await page.waitForTimeout(3500);
  const frames=await page.evaluate(()=>window.__headerFrames);assert.ok(frames.length>0);
  const initial=frames[0],last=frames.at(-1);assert.ok(initial.h<150);for(const frame of frames){assert.ok(Math.abs(frame.h-last.h)<2,JSON.stringify({width,scenario,frame,last}));assert.ok(Math.abs(frame.cardX-last.cardX)<2,JSON.stringify({width,scenario,frame,last}));}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth),0);
  assert.ok(await page.locator('#importLayoutToggle').count()===1);
  const shot=`${out}/${width}-${scenario}.png`;await page.screenshot({path:shot});
  report.push({width,height,scenario,initial,last,screenshot:shot});
 }
 assert.ok(served.has('/index.html')&&served.has('/css/daw.css')&&served.has('/js/studioLayout.js'));
 await page.locator('#importLayoutToggle').focus();await page.keyboard.press('Space');await page.waitForTimeout(150);assert.equal(await page.locator('#headerImportWorkspace').isVisible(),true);await page.keyboard.press('Escape');assert.equal(await page.locator('#headerImportWorkspace').isVisible(),false);
 const extraObservers=await page.evaluate(async()=>{const s=await import('/js/studioLayout.js'),v=await import('/js/headerCompactV2.js'),w=await import('/js/headerCompactV3.js'),r=await import('/js/headerReextract.js');const original=window.MutationObserver;let count=0;window.MutationObserver=class extends original{constructor(cb){super(cb);count++}};try{for(let i=0;i<3;i++){s.initStudioLayout();v.initHeaderCompactV2();w.initHeaderCompactV3();r.initHeaderReextract();}}finally{window.MutationObserver=original}return count});assert.equal(extraObservers,0);
 for(const id of ['importLayoutToggle','headerImportWorkspace','reextractCurrentTrack','availableLanes'])assert.equal(await page.locator('#'+id).count(),1,id);
 await page.locator('.cat-item[data-id="2e2c72eee977"]').dblclick();await page.waitForTimeout(2000);assert.match(await page.locator('#title').innerText(),/CPM22/i);await page.locator('#t-play').click();await page.waitForTimeout(2500);let elapsed=await page.locator('#footer-time-elapsed').innerText();assert.notEqual(elapsed,'00:00');await page.locator('#t-play').click();await page.locator('#studioKaraokeTab').click();await page.locator('#studioWaveformsTab').click();
 const geometry=await page.evaluate(()=>{const rect=s=>{const e=document.querySelector(s),r=e?.getBoundingClientRect();return r&&{x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};return {header:rect('.daw-topbar'),form:rect('#job-form'),card:rect('#nowPlayingPanel'),transport:rect('.footer-group-transport'),speed:rect('.footer-group-speed'),export:rect('#t-export-btn'),below:rect('.daw-body')}});console.log('GEOMETRY',width,JSON.stringify(geometry));await page.screenshot({path:`${out}/${width}-selected.png`});for(const key of ['transport','speed','export']){const r=geometry[key];assert.ok(r&&r.width>0&&r.height>0,key+' hidden');assert.ok(r.x>=geometry.card.x-1&&r.right<=geometry.card.right+1,`${key} outside card horizontally: ${JSON.stringify(geometry)}`);assert.ok(r.y>=geometry.card.y-1&&r.bottom<=geometry.card.bottom+1,`${key} outside card: ${JSON.stringify(geometry)}`);assert.ok(r.bottom<=geometry.below.y+1,`${key} overlaps lower panel`)}for(const [a,b] of [['transport','speed'],['transport','export'],['speed','export']]){const x=geometry[a],y=geometry[b];assert.ok(x.right<=y.x+1||y.right<=x.x+1||x.bottom<=y.y+1||y.bottom<=x.y+1,`${a} overlaps ${b}`)}await page.reload();await page.waitForTimeout(1800);report.push({width,height,scenario:'selected-reload',geometry,title:await page.locator('#title').innerText(),elapsed,errors});assert.deepEqual(errors,[]);
 await page.close();
 const nojs=await browser.newPage({viewport:{width,height},javaScriptEnabled:false});
 await nojs.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin==='http://127.0.0.1:8159'&&(u.pathname==='/'||u.pathname.startsWith('/css/'))){const rel=u.pathname==='/'?'/index.html':u.pathname;try{return route.fulfill({status:200,body:await readFile(root+rel),contentType:rel.endsWith('.css')?'text/css':'text/html'})}catch{}}return route.continue()});
 await nojs.goto('http://127.0.0.1:8159/');const check=nojs.locator('#importLayoutToggle');await check.focus();await nojs.keyboard.press('Space');assert.equal(await nojs.locator('#headerImportWorkspace').isVisible(),true);await nojs.keyboard.press('Space');assert.equal(await nojs.locator('#headerImportWorkspace').isVisible(),false);await nojs.screenshot({path:`${out}/${width}-no-js.png`});await nojs.close();
}
await writeFile(out+'/results.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));await browser.close();
