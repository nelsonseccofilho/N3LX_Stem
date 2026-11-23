// C34 — packaged N3LX_Stem.exe, real BrowserWindow resize and profile re-open.
// Requires the synthetic isolated launcher; never uses the personal library.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve, relative, isAbsolute } from 'node:path';
import { createConnection } from 'node:net';
import { setTimeout as sleep } from 'node:timers/promises';

const runtime=process.env.C34_RUNTIME;
const report=process.env.C34_REPORT;
const exe=process.env.C34_EXE;
const port=Number(process.env.C34_PORT);
const revision=process.env.C34_REVISION;
assert.ok(runtime&&report&&exe&&revision);
assert.ok(Number.isInteger(port)&&port>=1024&&port<=65535&&!([8159,8162].includes(port)));
assert.ok(existsSync(exe));
const inside=relative(resolve(join(report,'bundle')),resolve(exe));
assert.ok(inside&&!inside.startsWith('..')&&!isAbsolute(inside),'EXE must be inside this QA report');
const { _electron:electron }=createRequire(join(runtime,'package.json'))('playwright');
const profile=join(report,'profile'),exportsFolder=join(report,'exports');
const origin='http://127.0.0.1:'+port;
mkdirSync(profile,{recursive:true});mkdirSync(exportsFolder,{recursive:true});
writeFileSync(join(profile,'storage-preferences.json'),
  JSON.stringify({exportsFolder}),{flag:'wx',encoding:'utf8'});
const safeEnv=Object.fromEntries(Object.entries(process.env).filter(([k])=>
  !k.startsWith('N3LX_')&&!k.startsWith('STEMDECK_')&&!k.startsWith('C3')&&
  k!=='ELECTRON_RUN_AS_NODE'));
const results=[],errors=[];
let active=null,failure=null,firstBackendPid=null;

// A packaged Electron window owns its Python server. app.close() completes
// before the parent-death watchdog (1s polling) necessarily releases the
// listening port. Reopening earlier can attach to a backend already shutting
// down, then show ERR_FAILED(-2) loading the localhost URL.
function portOccupied(){
  return new Promise((resolveOccupied,reject)=>{
    const socket=createConnection({host:'127.0.0.1',port});
    let settled=false;
    function finish(value){
      if(settled)return;
      settled=true;
      socket.destroy();
      resolveOccupied(value);
    }
    socket.once('connect',()=>finish(true));
    socket.once('error',error=>{
      if(error?.code==='ECONNREFUSED')finish(false);
      else reject(error);
    });
    socket.setTimeout(1500,()=>finish(true));
  });
}

async function waitForFirstBackendToExit(){
  const deadline=Date.now()+45000;
  while(Date.now()<deadline){
    if(!(await portOccupied())){
      // Confirm the port stays free: do not treat a single failed connect
      // during teardown as evidence the backend has finished.
      await sleep(400);
      if(!(await portOccupied())){
        results.push({test:'first packaged backend exited before reopen',result:'PASS'});
        console.log('PASS C34: first packaged backend stopped before reopen');
        return;
      }
    }
    await sleep(250);
  }
  throw new Error('First packaged backend did not release QA port within 45s; no forced stop');
}

async function launch(label){
  const app=await electron.launch({
    executablePath:exe,args:['--port='+port],cwd:join(report,'bundle'),
    env:{...safeEnv,N3LX_STEM_RUNTIME_DIR:runtime,
      N3LX_STEM_DATA_DIR:join(report,'data'),N3LX_STEM_PROFILE_DIR:profile},
    timeout:180000,
  });
  active={app,page:null};
  const page=await app.firstWindow({timeout:180000});active.page=page;
  page.on('pageerror',e=>errors.push(String(e)));
  await page.locator('#studioWaveformsTab').waitFor({state:'visible',timeout:30000});
  assert.equal(new URL(page.url()).origin,origin);
  const health=await (await page.request.get(origin+'/api/health',{timeout:10000})).json();
  assert.equal(health.product,'N3LX_Stem');
  assert.equal(health.status,'ok');
  assert.ok(health.instance);
  assert.ok(Number.isInteger(health.pid) && health.pid > 0,
    'Backend PID missing from health endpoint');
  if(label==='first')firstBackendPid=health.pid;
  else assert.notEqual(health.pid,firstBackendPid,
    'Reopen reused the prior backend instead of starting a fresh instance');
  const jobs=await (await page.request.get(origin+'/api/jobs',{timeout:10000})).json();
  assert.deepEqual(jobs.map(x=>x.job_id).sort(),['e2e0cafebabe','e2e0deadbeef']);
  const info=await page.evaluate(()=>window.n3lxStorage.getInfo());
  assert.equal(resolve(info.exportsFolder).toLowerCase(),resolve(exportsFolder).toLowerCase());
  assert.equal(info.configured,true);
  assert.equal(info.exportsAvailable,true);
  results.push({test:'packaged startup '+label+' and isolated exports preference',result:'PASS'});
  console.log('PASS C34: packaged startup '+label+' and profile');
  return {app,page};
}

async function closeApp(){
  if(!active)return;
  const {app}=active;
  // The packaged EXE owns its backend. Closing the window can trigger the
  // parent watchdog and take HTTP offline before a late dynamic import loads.
  // Do not depend on GET /js/queue.js during shutdown: Electron closes the
  // renderer connections, while the outer Git Bash harness independently
  // verifies the exact backend identity, idle state and free QA port.
  // Unlike C32, this is NOT an independently managed dev renderer.
  try{await app.close();}catch(e){failure ||= 'Unable to close packaged app: '+String(e);}
  active=null;
}

try{
  const {app,page}=await launch('first');
  for(const [width,height] of [[1200,800],[900,700],[1366,786]]){
    const native=await app.evaluate(({BrowserWindow},size)=>{
      const w=BrowserWindow.getAllWindows()[0];
      if(!w||w.isDestroyed())throw new Error('No native window');
      w.setSize(size.width,size.height);
      return {size:w.getSize(),min:w.getMinimumSize(),visible:w.isVisible(),title:w.getTitle()};
    },{width,height});
    assert.deepEqual(native.size,[width,height]);
    assert.ok(native.visible&&native.title.includes('N3LX_Stem'));
    assert.ok(width>=native.min[0]&&height>=native.min[1]);
    await page.waitForTimeout(200);
    const renderer=await page.evaluate(()=>({
      width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth-innerWidth,
      playable:document.querySelector('#t-play')?.getBoundingClientRect().width>0,
    }));
    assert.ok(renderer.width>0&&renderer.width<=width);
    assert.ok(renderer.height>0&&renderer.height<=height);
    assert.ok(renderer.overflow<=1,'Horizontal overflow after native resize');
    assert.equal(renderer.playable,true);
    await page.screenshot({path:join(report,'native-'+width+'x'+height+'.png')});
    results.push({test:'native resize '+width+'x'+height,result:'PASS',native,renderer});
    console.log('PASS C34: native resize '+width+'x'+height);
  }
  await page.evaluate(()=>window.n3lxAppearance.setTheme('dark'));
  await page.waitForTimeout(200);
  assert.equal(await app.evaluate(({nativeTheme})=>nativeTheme.themeSource),'dark');
  results.push({test:'native theme IPC',result:'PASS'});
  console.log('PASS C34: appearance IPC');
  await closeApp();
  await waitForFirstBackendToExit();
  const reopened=await launch('reopened');
  results.push({test:'close/reopen packaged EXE and persisted isolated profile',result:'PASS'});
  console.log('PASS C34: close/reopen with new backend PID');
  // The old watchdog polls every second. A delayed failure may otherwise
  // happen after the test claimed success. Keep the new window alive beyond
  // that interval and reload from the backend to verify it remains stable.
  await sleep(2500);
  const stableHealth=await (await reopened.page.request.get(
    origin+'/api/health',{timeout:10000})).json();
  assert.equal(stableHealth.status,'ok');
  assert.notEqual(stableHealth.pid,firstBackendPid);
  await reopened.page.reload({waitUntil:'load',timeout:30000});
  await reopened.page.locator('#studioWaveformsTab').waitFor({state:'visible',timeout:15000});
  results.push({test:'reopened packaged backend remains alive and page reloads',result:'PASS'});
  console.log('PASS C34: reopened backend stable and reloadable');
  assert.deepEqual(errors,[]);
}catch(e){
  failure=String(e?.stack||e);
  console.error(failure);
  if(active?.page&&!active.page.isClosed())
    await active.page.screenshot({path:join(report,'native-failure.png')}).catch(()=>{});
}finally{
  await closeApp();
  writeFileSync(join(report,'native-qa.json'),JSON.stringify({
    revision,mode:'real Windows packaged EXE, not developer Electron',
    source:'synthetic isolated jobs',hardwareAudioVerified:false,
    setupInstallerVerified:false,passed:!failure,results,errors,
    ...(failure?{failure}:{})
  },null,2));
}
if(failure)process.exitCode=1;
