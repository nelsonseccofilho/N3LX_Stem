// Run against the isolated seeded QA server only. No real model is invoked.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.N3LX_PLAYWRIGHT || 'playwright');
(async () => {
 const out=process.env.N3LX_QA_OUTPUT || 'test-results/ux-release';fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:process.env.N3LX_QA_BROWSER || 'msedge'});
 const page=await browser.newPage({viewport:{width:1280,height:800},locale:'pt-BR'});
 const errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
 const check=(name,value)=>{assert.ok(value,name);checks.push(name)};
 try {
 await page.request.post((process.env.N3LX_QA_URL || 'http://127.0.0.1:8139') + '/api/ui-store', {data:{values:{'stemdeck.language':'pt'}}});
 await page.goto(process.env.N3LX_QA_URL || 'http://127.0.0.1:8139');
 await page.locator('.cat-item').first().waitFor();
 await page.locator('.cat-item').first().click();
 await page.waitForFunction(()=>!document.querySelector('.app').classList.contains('no-track') && !document.querySelector('.app').classList.contains('is-processing-track'));
 await page.locator('#importLayoutToggle').filter({hasText:'Nova extração'}).waitFor();
 check('PT dynamic controls on initial render',(await page.locator('#reextractCurrentTrack').innerText()).includes('Reextrair'));
 await page.screenshot({path:path.join(out,'studio-1280-pt.png')});
 await page.locator('#studioKaraokeTab').click();
 check('Karaoke hides waveform panel',await page.locator('#lanes').isHidden());
 check('Karaoke selected semantics',await page.locator('#studioKaraokeTab').getAttribute('aria-selected')==='true');
 await page.locator('#studioKaraokeTab').press('ArrowRight');
 check('Karaoke tabs wrap with arrow key',await page.locator('#studioWaveformsTab').getAttribute('aria-selected')==='true');
 await page.locator('#studioWaveformsTab').press('End');
 await page.screenshot({path:path.join(out,'karaoke-1280-pt.png')});
 await page.locator('#studioWaveformsTab').click();
 await page.locator('#settingsBtn').click();
 await page.locator('.settings-tab[data-tab="details"]').click();
 check('Settings active tab semantics',await page.locator('.settings-tab[data-tab="details"]').getAttribute('aria-selected')==='true');
 const select=page.locator('.set-transcribe-lyrics');
 await select.scrollIntoViewIfNeeded();
 check('Transcription label fits',await select.evaluate(el=>el.clientWidth>=200));
 const overflow=await page.locator('.library-editor').evaluate(el=>el.scrollWidth>el.clientWidth);
 check('Settings no horizontal overflow at 1280',!overflow);
 await page.screenshot({path:path.join(out,'settings-details-1280-pt.png')});
 await page.locator('.settings-done').focus();await page.keyboard.press('Tab');
 check('Settings traps Tab',await page.locator('.library-editor-close').evaluate(el=>el===document.activeElement));
 await page.keyboard.press('Shift+Tab');
 check('Settings traps Shift+Tab',await page.locator('.settings-done').evaluate(el=>el===document.activeElement));
 await page.locator('.settings-tab[data-tab="details"]').focus();await page.keyboard.press('ArrowRight');
 check('Settings arrow tabs',await page.locator('.settings-tab[data-tab="network"]').getAttribute('aria-selected')==='true');
 for(const width of [1080,800,640]) {
   await page.setViewportSize({width,height:720});
   await page.locator('.settings-tab[data-tab="details"]').click();
   await select.scrollIntoViewIfNeeded();
   check(`Settings no overflow at ${width}`,await page.locator('.library-editor').evaluate(el=>el.scrollWidth<=el.clientWidth));
   check(`Settings footer visible at ${width}`,await page.locator('.settings-done').evaluate(el=>el.getBoundingClientRect().bottom<=innerHeight));
   await page.screenshot({path:path.join(out,`settings-${width}-pt.png`)});
 }
 await page.setViewportSize({width:1280,height:800});
 await page.locator('.settings-tab[data-tab="general"]').click();
 await page.locator('.set-language').focus();
 await page.locator('.set-language').selectOption('en');
 await page.locator('.settings-done').filter({hasText:'Done'}).waitFor();
 check('Language change retains category',await page.locator('.settings-tab[data-tab="general"]').getAttribute('aria-selected')==='true');
 check('Language change keeps focus',await page.locator('.set-language').evaluate(el=>el===document.activeElement));
 await page.locator('.settings-tab[data-tab="details"]').click();
 await page.screenshot({path:path.join(out,'settings-details-1280-en.png')});
 await page.keyboard.press('Escape');
 check('Escape closes settings',await page.locator('.library-editor').count()===0);
 check('Dialog restores opener',await page.locator('#settingsBtn').evaluate(el=>el===document.activeElement));
 check('EN dynamic controls',(await page.locator('#reextractCurrentTrack').innerText()).includes('Re-extract'));
 // Exercise the failure path without launching an extraction or touching source audio.
 await page.locator('#submit').evaluate(el=>{el.dataset.resplitJob='e2e0deadbeef';el.dataset.resplitTitle='Synthetic song';el.disabled=false});
 await page.route('**/api/jobs/e2e0deadbeef/resplit',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Synthetic request failure'})}));
 await page.locator('#reextractCurrentTrack').click();
 await page.waitForFunction(()=>!document.querySelector('#submit').classList.contains('loading'));
 check('Failed re-extraction can be retried',await page.locator('#reextractCurrentTrack').isEnabled());
 await page.locator('#importLayoutToggle').click();
 await page.locator('#url').fill('new import');
 check('Staged import blocks re-extraction',await page.locator('#reextractCurrentTrack').isDisabled());
 await page.locator('#url').fill('');
 check('Cleared import restores re-extraction',await page.locator('#reextractCurrentTrack').isEnabled());
 check('No browser execution errors',errors.length===0);
 console.log(JSON.stringify({passed:checks.length,checks,errors},null,2));
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({passed:checks.length,checks,errors},null,2));
 } catch(error) {await page.screenshot({path:path.join(out,'failure.png')});throw error;}
 finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});

