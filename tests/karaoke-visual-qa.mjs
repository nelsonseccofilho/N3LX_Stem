import {chromium} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const out=resolve(process.env.KARAOKE_QA_EVIDENCE || 'test-results/karaoke-cinema');await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge'});
try {
 const page=await browser.newPage({viewport:{width:1920,height:1080}});
 await page.route('**/*',async route=>{const r=route.request(),u=new URL(r.url());if(!['GET','HEAD'].includes(r.method()))return route.abort();if(u.origin==='http://127.0.0.1:8159'&&(u.pathname==='/'||/^\/(js|css)\//.test(u.pathname))){const p=u.pathname==='/'?'/index.html':u.pathname;return route.fulfill({body:await readFile(resolve('static')+p),contentType:p.endsWith('.js')?'text/javascript':p.endsWith('.css')?'text/css':'text/html'});}return route.continue();});
 await page.goto('http://127.0.0.1:8159/');
 await page.locator('.cat-item[data-id="2e2c72eee977"]').dblclick();
 await page.locator('#studioKaraokeTab').click();await page.waitForTimeout(2500);
 await page.screenshot({path:out+'/1920-loaded.png'});
 const results=[];
 for(const [width,height] of [[1920,1080],[1440,900],[1366,786]]) {
  await page.setViewportSize({width,height});
  await page.locator('#karaokeCinemaOpen').click();
  await page.waitForFunction(()=>!!document.fullscreenElement);
  await page.waitForTimeout(300);
  if(width===1920){
   const timings=await page.evaluate(async()=>{const t=await import('/js/transport.js');const values=[];for(const el of document.querySelectorAll('.lyrics-line')){el.click();values.push({text:el.textContent,time:t.transport().getCurrentTime()});}return values;});
   await writeFile(out+'/line-times.json',JSON.stringify(timings,null,2));
   const temporal=[];
   for(const [time,kind,text] of [[75,'message','Instrumental'],[78.5,'current','Não sei viver sem ter você'],[83,'message','Instrumental'],[88,'current','É difícil de aceitar'],[229,'message','Fim da letra']]){
    await page.evaluate(async time=>{const t=await import('/js/transport.js');t.setPlayheadTime(time);},time);
    await page.waitForTimeout(150);
    const el=page.locator(kind==='message'?'#cinemaTimingMessage':'.lyrics-line.current');
    if(!await el.isVisible()||await el.innerText()!==text)throw new Error(`Temporal ${time}: expected ${text}, got ${await el.textContent()}`);
    if(await page.locator('.lyrics-line.current .singing').count())throw new Error(`Animation during gap ${time}`);
    await page.screenshot({path:out+`/time-${time}.png`});temporal.push({time,kind,text,result:'PASS'});
   }
   await writeFile(out+'/temporal-results.json',JSON.stringify(temporal,null,2));
   await page.evaluate(async()=>{const t=await import('/js/transport.js');t.setPlayheadTime(78.5);t.togglePlayPause();});
   for(let attempt=0;attempt<40;attempt++){
    if(await page.evaluate(async()=> (await import('/js/transport.js')).transport().getCurrentTime())>80.3)break;
    await page.waitForTimeout(500);
   }
   const playing=await page.evaluate(async()=> (await import('/js/transport.js')).transport().getCurrentTime());
   if(playing<80.3)throw new Error('playback clock did not advance: '+playing);
   if(await page.locator('.lyrics-line.current').innerText()!=='Não sei viver sem ter você')throw new Error('vocal entry wrong');
   await page.evaluate(async()=> (await import('/js/transport.js')).togglePlayPause());
   await page.waitForTimeout(100);
   const frozen=await page.locator('.lyrics-line.current').innerHTML();
   const stopped=await page.evaluate(async()=> (await import('/js/transport.js')).transport().getCurrentTime());
   await page.waitForTimeout(500);
   if(frozen!==await page.locator('.lyrics-line.current').innerHTML())throw new Error('word animation advances while paused');
   if(Math.abs(stopped-await page.evaluate(async()=> (await import('/js/transport.js')).transport().getCurrentTime()))>.02)throw new Error('clock advances paused');
   await page.screenshot({path:out+'/paused-vocal.png'});
  }
  await page.evaluate(async()=>{const t=await import('/js/transport.js');t.setPlayheadTime(233);});
  await page.waitForTimeout(250);
  if(await page.locator('.lyrics-line.current').count() && /Não há mais desculpas/.test(await page.locator('.lyrics-line.current').innerText()))throw new Error('final seeks back to first phrase');
  await page.screenshot({path:out+`/${width}-ending.png`});
  await page.evaluate(async()=>{const t=await import('/js/transport.js');t.setPlayheadTime(60);});
  await page.waitForTimeout(250);
  await page.screenshot({path:out+`/${width}-seek60.png`});
  await page.locator('#t-pitch-reset').click();
  await page.waitForFunction(()=>document.querySelector('#cinemaKey').textContent==='G maior → G maior');
  for(let i=0;i<2;i++)await page.locator('#t-pitch-up').click();
  await page.waitForFunction(()=>document.querySelector('#cinemaKey').textContent==='G maior → A maior');
  if(await page.locator('#t-pitch-value').innerText()!=='+2')throw new Error('pitch listener duplicated');
  await page.screenshot({path:out+`/${width}-pitch-plus2.png`});
  for(let i=0;i<4;i++)await page.locator('#t-pitch-down').click();
  await page.waitForFunction(()=>document.querySelector('#cinemaKey').textContent==='G maior → F maior');
  if(await page.locator('#t-pitch-value').innerText()!=='-2')throw new Error('pitch state mismatch');
  await page.locator('#t-pitch-reset').click();
  await page.waitForFunction(()=>document.querySelector('#cinemaKey').textContent==='G maior → G maior');
  await page.locator('#t-pitch-up').focus();await page.keyboard.press('Shift+Tab');
  if(!await page.evaluate(()=>document.fullscreenElement.contains(document.activeElement)))throw new Error('focus outside cinema');
  const state=await page.evaluate(()=>({fullscreen:document.fullscreenElement?.id,key:document.querySelector('#cinemaKey').textContent,exit:document.querySelector('#karaokeCinemaExit').getBoundingClientRect().toJSON(),controls:document.querySelectorAll('#t-pitch-up').length}));
  await page.screenshot({path:out+`/${width}-cinema.png`});
  if(state.fullscreen!=='karaokeStage'||state.controls!==1||state.exit.bottom>height||state.exit.y<height-100)throw new Error(JSON.stringify(state));
  await page.locator('#karaokeCinemaExit').click();
  await page.waitForFunction(()=>!document.fullscreenElement);
  if(!await page.locator('#karaokeCinemaOpen').evaluate(el=>el===document.activeElement))throw new Error('focus not restored');
  if(!await page.locator('#nowPlayingPanel #t-pitch-up').count())throw new Error('pitch not restored');
  await page.locator('#karaokeCinemaOpen').click();await page.waitForFunction(()=>!!document.fullscreenElement);
  await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.fullscreenElement);
  if(!await page.locator('#karaokeCinemaOpen').evaluate(el=>el===document.activeElement))throw new Error('Escape focus');
  results.push({width,height,...state});
 }
 await writeFile(out+'/fullscreen-results.json',JSON.stringify(results,null,2));
 const data=await page.evaluate(async()=>({text:document.querySelector('#lyricsBody')?.innerText,lyrics:await fetch('/api/jobs/2e2c72eee977/lyrics').then(r=>r.json())}));
 await writeFile(out+'/inspection.json',JSON.stringify(data,null,2));
 console.log(JSON.stringify(data).slice(0,2200));
} finally {await browser.close();}
