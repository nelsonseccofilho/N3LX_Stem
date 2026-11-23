// C35 — actual packaged Electron UI playback and native WAV export.
// Synthetic test only. A moving clock does not prove physical speaker output.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {existsSync,readFileSync,writeFileSync} from 'node:fs';
import {join,resolve,relative,isAbsolute} from 'node:path';
import {spawnSync} from 'node:child_process';
import {setTimeout as sleep} from 'node:timers/promises';

const runtime=process.env.C34_RUNTIME;
const report=process.env.C34_REPORT;
const exe=process.env.C34_EXE;
const port=Number(process.env.C34_PORT);
const revision=process.env.C34_REVISION;
assert.ok(runtime&&report&&exe&&revision);
assert.ok(Number.isInteger(port)&&port>1023&&!([8159,8162].includes(port)));
const rel=relative(resolve(join(report,'bundle')),resolve(exe));
assert.ok(rel&&!rel.startsWith('..')&&!isAbsolute(rel)&&existsSync(exe));
const {_electron:electron}=createRequire(join(runtime,'package.json'))('playwright');
const origin='http://127.0.0.1:'+port;
const output=join(report,'exports','c35-synthetic.wav');
const safeEnv=Object.fromEntries(Object.entries(process.env).filter(([k])=>
  !k.startsWith('N3LX_')&&!k.startsWith('STEMDECK_')&&!k.startsWith('C3')&&
  k!=='ELECTRON_RUN_AS_NODE'));
const results=[],errors=[];
let app=null,page=null,failure=null;

try{
  app=await electron.launch({
    executablePath:exe,args:['--port='+port],cwd:join(report,'bundle'),
    timeout:180000,
    env:{...safeEnv,N3LX_STEM_RUNTIME_DIR:runtime,
      N3LX_STEM_DATA_DIR:join(report,'data'),
      N3LX_STEM_PROFILE_DIR:join(report,'profile')}
  });
  page=await app.firstWindow({timeout:180000});
  page.on('pageerror',e=>errors.push(String(e)));
  const track=page.locator('.cat-item[data-id="e2e0cafebabe"]');
  await track.waitFor({state:'visible',timeout:30000});
  assert.equal(new URL(page.url()).origin,origin);
  await track.dblclick();
  await page.waitForFunction(()=>document.querySelector('#footer-time-total')
    ?.textContent?.trim()==='00:02',null,{timeout:15000});

  // Gentle QA monitoring gain, not a change to the exported mix.
  await page.locator('#t-master').evaluate(el=>{
    el.value='0.15';
    el.dispatchEvent(new Event('input',{bubbles:true}));
  });
  await page.locator('#t-play').click();
  await page.waitForFunction(()=>document.querySelector('#t-play')
    ?.classList.contains('playing'),null,{timeout:5000});
  await page.waitForFunction(()=>{
    const t=document.querySelector('#footer-time-elapsed')?.textContent?.trim();
    return t&&t!=='00:00';
  },null,{timeout:6000});
  await page.locator('#t-stop').click();
  results.push({test:'packaged real UI Play advances synthetic transport',result:'PASS'});
  console.log('PASS C35: real packaged UI Play and clock');

  // Observe Electron's actual DownloadItem, not a direct GET to the endpoint.
  // Only the specific fixture WAV is allowed to write into this QA report.
  await app.evaluate(({BrowserWindow},opts)=>{
    const win=BrowserWindow.getAllWindows()[0];
    if(!win||win.isDestroyed())throw Error('No native packaged window');
    globalThis.__c35Download={state:'awaiting'};
    win.webContents.session.on('will-download',(_event,item)=>{
      const url=item.getURL();
      if(!url.startsWith(opts.expected)){
        globalThis.__c35Download={state:'unexpected',url};
        item.cancel();
        return;
      }
      item.setSavePath(opts.target);
      globalThis.__c35Download={state:'started',url};
      item.once('done',(_e,state)=>{
        globalThis.__c35Download={state,url};
      });
    });
  },{expected:origin+'/api/jobs/e2e0cafebabe/mixdown.wav?',target:output});

  await page.locator('#t-export-btn').click();
  assert.equal(await page.locator('#t-fmt-wav').getAttribute('aria-checked'),'true');
  await page.locator('#t-export-mix').click();
  let download;
  for(let n=0;n<120;n++){
    download=await app.evaluate(()=>globalThis.__c35Download);
    if(download?.state==='completed')break;
    if(['cancelled','interrupted','unexpected'].includes(download?.state)){
      throw Error('Native download did not complete: '+JSON.stringify(download));
    }
    await sleep(250);
  }
  assert.equal(download?.state,'completed','Native WAV download timed out');
  assert.ok(existsSync(output));
  const file=readFileSync(output);
  assert.equal(file.toString('ascii',0,4),'RIFF');
  assert.equal(file.toString('ascii',8,12),'WAVE');
  assert.ok(file.length>20000,'WAV export unexpectedly small');
  const ff=spawnSync('ffprobe',['-v','error','-show_entries',
    'stream=codec_type,channels','-of','json',output],
    {encoding:'utf8',timeout:15000});
  assert.equal(ff.status,0,'Invalid audio export: '+ff.stderr);
  assert.ok(JSON.parse(ff.stdout).streams.some(s=>s.codec_type==='audio'&&s.channels===2));
  results.push({test:'native Export Mix from UI creates valid stereo WAV in QA folder',
    result:'PASS',bytes:file.length});
  console.log('PASS C35: native UI WAV download and FFprobe');

  await page.locator('#t-play').click();
  await page.waitForFunction(()=>document.querySelector('#t-play')?.classList.contains('playing'),
    null,{timeout:5000});
  await app.close();
  app=null;
  results.push({test:'normal EXE close during active synthetic playback',result:'PASS'});
  console.log('PASS C35: safe native close during playback');
  assert.deepEqual(errors,[]);
}catch(e){
  failure=String(e?.stack||e);console.error(failure);
  if(page&&!page.isClosed())
    await page.screenshot({path:join(report,'audio-failure.png')}).catch(()=>{});
}finally{
  if(app)try{await app.close();}catch(e){failure||='EXE close failed: '+String(e);}
  writeFileSync(join(report,'audio-qa.json'),JSON.stringify({
    revision,kind:'C35 packaged Windows synthetic audio',
    hardwareAudibilityVerified:false,outputSwitchVerified:false,
    passed:!failure,results,errors,...(failure?{failure}:{})
  },null,2));
}
if(failure)process.exitCode=1;
