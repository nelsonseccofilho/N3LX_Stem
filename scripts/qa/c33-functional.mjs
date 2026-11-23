// C33 functional QA — real Electron UI and real API exports, synthetic inputs only.
// Launched by the proven C32 isolated lifecycle harness when N3LX_C33_FUNCTIONAL=1.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

// seed.py creates two records with the same source_url. The catalog deduplicates
// them, leaving the sibling already selected by the C32 smoke scenario.
const ID = 'e2e0cafebabe';

async function assertProbe(file, wanted) {
  const result = spawnSync('ffprobe', [
    '-v', 'error', '-show_entries', 'stream=codec_type',
    '-of', 'json', file,
  ], { encoding: 'utf8', timeout: 15000 });
  assert.equal(result.status, 0, 'ffprobe failed: ' + result.stderr);
  const types = JSON.parse(result.stdout).streams.map(x => x.codec_type);
  for (const type of wanted)
    assert.ok(types.includes(type), 'Missing ' + type + ' stream: ' + types.join(','));
  return types;
}

function assertStereoWavPan(buffer) {
  assert.equal(buffer.toString('ascii', 0, 4), 'RIFF');
  assert.equal(buffer.toString('ascii', 8, 12), 'WAVE');
  let channels = 0, bits = 0, dataStart = -1, dataSize = 0;
  for (let offset = 12; offset + 8 <= buffer.length;) {
    const id = buffer.toString('ascii', offset, offset + 4);
    const size = buffer.readUInt32LE(offset + 4);
    if (id === 'fmt ') {
      channels = buffer.readUInt16LE(offset + 10);
      bits = buffer.readUInt16LE(offset + 22);
    }
    if (id === 'data') { dataStart = offset + 8; dataSize = size; break; }
    offset += 8 + size + (size & 1);
  }
  assert.equal(channels, 2, 'Must preserve stereo output');
  assert.equal(bits, 16, 'WAV export must be PCM16');
  assert.ok(dataStart > 0 && dataSize > 10000);
  const frames = Math.min(8192, Math.floor(Math.min(dataSize, buffer.length - dataStart) / 4));
  assert.ok(frames > 1000);
  let leftEnergy = 0, rightEnergy = 0;
  for (let i = 0; i < frames; i++) {
    const off = dataStart + i * 4;
    const l = buffer.readInt16LE(off), r = buffer.readInt16LE(off + 2);
    leftEnergy += l * l;
    rightEnergy += r * r;
  }
  const lRms = Math.sqrt(leftEnergy / frames), rRms = Math.sqrt(rightEnergy / frames);
  assert.ok(lRms > 500, 'Expected audible left channel');
  assert.ok(rRms < lRms * 0.02, 'Hard-left pan leaked into right channel');
  return { channels, bits, frames, leftRms: Math.round(lRms), rightRms: Math.round(rRms) };
}

export async function runC33Functional({ page, report, port }) {
  const results = [];
  await page.locator('#studioWaveformsTab').click();
  // C32 has already opened the 2-second sibling. Do not re-open the fixture's
  // original ID: catalog deduplication intentionally removes it from the UI.
  await page.locator('.cat-item[data-id="' + ID + '"]').waitFor({ state: 'visible', timeout: 10000 });
  await page.waitForFunction(() =>
    document.querySelector('#footer-time-total')?.textContent?.trim() === '00:02',
    null, { timeout: 10000 });

  // Actual transport and clock advance with 2s synthetic stems, not mocked audio.
  const play = page.locator('#t-play');
  await play.click();
  await page.waitForFunction(() => document.querySelector('#t-play')?.classList.contains('playing'),
    null, { timeout: 6000 });
  await page.waitForFunction(() => {
    const text = document.querySelector('#footer-time-elapsed')?.textContent?.trim();
    return text && text !== '00:00';
  }, null, { timeout: 6000 });
  await page.locator('#t-stop').click();
  await page.waitForFunction(() =>
    document.querySelector('#footer-time-elapsed')?.textContent?.trim() === '00:00',
    null, { timeout: 4000 });
  results.push({ test: 'real synthetic WAV playback, time advances, stop resets', result: 'PASS' });
  console.log('PASS C33: playback and transport');

  // Mixer controls in real Electron renderer (no browser-only fake Tauri bridge).
  for (const selector of ['.mixer-column .mute:visible:enabled', '.mixer-column .solo:visible:enabled']) {
    const control = page.locator(selector).first();
    await control.waitFor({ state: 'visible', timeout: 10000 });
    await control.click();
    assert.equal(await control.getAttribute('aria-pressed'), 'true', selector);
    await control.click();
    assert.equal(await control.getAttribute('aria-pressed'), 'false', selector);
  }
  results.push({ test: 'mixer mute/solo round-trip', result: 'PASS' });
  console.log('PASS C33: mixer mute and solo');

  // Real loop editor interactions, matching the existing header-loop E2E.
  const options = page.locator('#song-loop-more');
  const start = page.locator('#t-loop-start');
  const end = page.locator('#t-loop-end');
  await options.click();
  await end.click();
  await end.fill('1.500');
  await start.click();
  await start.fill('0.500');
  await end.click();
  await page.waitForFunction(() =>
    document.querySelector('#t-loop')?.classList.contains('active'),
    null, { timeout: 4000 });
  await end.press('Escape');
  await options.click();
  assert.equal(await start.inputValue(), '00.500');
  assert.equal(await end.inputValue(), '01.500');
  await page.screenshot({ path: join(report, 'functional-loop.png') });
  results.push({ test: 'edit and preserve loop bounds', result: 'PASS' });
  console.log('PASS C33: loop bounds');

  // The real API renders actual audio. Hard-left pan provides a numeric stereo
  // assertion, not just a successful HTTP response or a rendered UI label.
  const base = 'http://127.0.0.1:' + port + '/api/jobs/' + ID;
  const wavResponse = await page.request.get(
    base + '/mixdown.wav?stems=vocals&gains=0.5&pans=-1', { timeout: 45000 });
  assert.equal(wavResponse.status(), 200, 'WAV HTTP status');
  const wav = await wavResponse.body();
  const pan = assertStereoWavPan(wav);
  const wavPath = join(report, 'functional-export-pan-left.wav');
  writeFileSync(wavPath, wav);
  await assertProbe(wavPath, ['audio']);
  results.push({ test: 'WAV PCM16 stereo hard-left pan', result: 'PASS', ...pan });
  console.log('PASS C33: real WAV render, stereo pan and ffprobe');

  // seed.py has no video by default: the isolated launcher generated a 2-second
  // black MP4 fixture solely in this QA directory. Exercise the real AAC/video
  // mux rather than treating the export menu's browser stub as evidence.
  const mp4Response = await page.request.get(
    base + '/video.mp4?stems=vocals,drums&gains=0.5,0.5&pans=-1,1',
    { timeout: 45000 });
  assert.equal(mp4Response.status(), 200, 'MP4 HTTP status');
  const mp4 = await mp4Response.body();
  assert.ok(mp4.length > 1000);
  assert.equal(mp4.toString('ascii', 4, 8), 'ftyp', 'Missing MP4 container signature');
  const mp4Path = join(report, 'functional-export-video.mp4');
  writeFileSync(mp4Path, mp4);
  const streams = await assertProbe(mp4Path, ['video', 'audio']);
  results.push({ test: 'MP4 video + AAC audio mux', result: 'PASS', bytes: mp4.length, streams });
  console.log('PASS C33: real MP4 video/audio mux and ffprobe');

  await page.screenshot({ path: join(report, 'functional-studio.png') });
  return results;
}
