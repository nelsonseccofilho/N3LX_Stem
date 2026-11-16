// Run: node tests/js/multitrack-playback.test.mjs
// Exercise mixed PCM16/PCM24/float32 files through public engine APIs.
import assert from "node:assert/strict";
import { createChunkedAudioEngine } from "../../static/js/chunkedAudioEngine.js";


const rate = 44100;
const frames = 64;
const values = [-8388608, -8388607, -65536, -256, -1, 0, 1, 255, 256, 65536, 8388607];
function wav(bits, format = 1, channels = 2) {
  const stride = bits / 8;
  const b = Buffer.alloc(44 + frames * channels * stride);
  b.write("RIFF"); b.writeUInt32LE(b.length - 8, 4); b.write("WAVEfmt ", 8);
  b.writeUInt32LE(16, 16); b.writeUInt16LE(format, 20);
  b.writeUInt16LE(channels, 22); b.writeUInt32LE(rate, 24);
  b.writeUInt32LE(rate * channels * stride, 28);
  b.writeUInt16LE(channels * stride, 32); b.writeUInt16LE(bits, 34);
  b.write("data", 36); b.writeUInt32LE(b.length - 44, 40);
  for (let i = 0; i < frames * channels; i++) {
    const at = 44 + i * stride;
    const value = values[i % values.length];
    if (format === 3) b.writeFloatLE(value / 8388608, at);
    else b.writeIntLE(bits === 16 ? value >> 8 : value, at, stride);
  }
  return b;
}

class Context {
  constructor() {
    this.currentTime = 0; this.sampleRate = rate; this.state = "running";
    this.destination = {}; this.sources = []; this.panners = []; this.audioWorklet = null;
  }
  addEventListener() {}
  removeEventListener() {}
  createGain() {
    const param = { value: 1, setTargetAtTime(v) { this.value = v; } };
    return { gain: param, connect(target) { this.target = target; }, disconnect() {} };
  }
  createAnalyser() { return { connect() {}, disconnect() {} }; }
  createStereoPanner() {
    const node = {
      pan: { value: 0, setTargetAtTime(v) { this.value = v; } },
      connect(target) { this.target = target; },
      disconnect() {},
    };
    this.panners.push(node);
    return node;
  }
  createBuffer(channels, length, sampleRate) {
    const data = Array.from({ length: channels }, () => new Float32Array(length));
    return { length, sampleRate, numberOfChannels: channels, duration: length / sampleRate,
      getChannelData(ch) { return data[ch]; } };
  }
  createBufferSource() {
    const source = { playbackRate: { value: 1 }, connect(target) { this.target = target; },
      start(when, offset) { this.started = { when, offset }; }, stop() {}, disconnect() {} };
    this.sources.push(source);
    return source;
  }
  async decodeAudioData(bytes) {
    if (new DataView(bytes).getUint16(20, true) === 99) throw new Error("unsupported format");
    return this.createBuffer(2, frames, rate);
  }
  async resume() {}
  async close() {}
}

globalThis.window = { AudioContext: Context };
const { createAudioEngine } = await import("../../static/js/audioEngine.js");
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => {};
const files = new Map();
globalThis.fetch = async (url, opts = {}) => {
  const file = files.get(url);
  if (!file) return { ok: false, status: 404 };
  const range = /bytes=(\d+)-(\d+)/.exec(opts.headers?.Range || "");
  const start = range ? Number(range[1]) : 0;
  const end = range ? Math.min(Number(range[2]), file.length - 1) : file.length - 1;
  const slice = file.subarray(start, end + 1);
  return { ok: true, status: range ? 206 : 200,
    headers: { get: () => `bytes ${start}-${end}/${file.length}` },
    arrayBuffer: async () => slice.buffer.slice(slice.byteOffset, slice.byteOffset + slice.length) };
};

// The complete profile used to start only seven lanes: the eight PCM24 lanes
// had no header, but ready still reported success because other files loaded.
const names = ["bass", "guitar", "piano", "other", "drum_kick", "drum_snare",
  "drum_toms", "drum_hh", "drum_ride", "drum_crash", "lead_vocals", "backing_vocals",
  "residual_mix", "residual_drums", "residual_vocals"];
const stems = names.map((name, i) => {
  const url = `/${name}.wav`;
  files.set(url, wav(i < 4 ? 16 : i < 12 ? 24 : 32, i < 12 ? 1 : 3));
  return { name, url };
});
{
  const ctx = new Context();
  const eng = createChunkedAudioEngine(stems, { context: ctx });
  assert.equal(await eng.ready, true);
  assert.equal(await eng.play(), true);
  const started = ctx.sources.filter(s => s.started);
  assert.equal(started.length, 15, "every active lane must have a scheduled source");
  assert.equal(new Set(started.map(s => s.started.when)).size, 1, "all lanes start together");
  assert.equal(new Set(started.map(s => s.started.offset)).size, 1, "all lanes have the same offset");
  for (let lane = 0; lane < started.length; lane++) {
    const buffer = started[lane].buffer;
    assert.equal(buffer.length, frames);
    for (let ch = 0; ch < 2; ch++) {
      for (let frame = 0; frame < frames; frame++) {
        const v = values[(frame * 2 + ch) % values.length];
        const expected = lane < 4 ? (v >> 8) / 32768 : v / 8388608;
        assert.equal(buffer.getChannelData(ch)[frame], expected, `${names[lane]} ch${ch} frame${frame}`);
      }
    }
  }
  eng.destroy();
  console.log("PASS: all 15 mixed-format lanes start together with exact signed samples on both channels");
}
// Mono and more-than-stereo must use the same correct interleaving/scale.
for (const channels of [1, 3]) {
  files.set("/pcm24.wav", wav(24, 1, channels));
  const ctx = new Context();
  const eng = createChunkedAudioEngine([{ name: "lead_vocals", url: "/pcm24.wav" }], { context: ctx });
  assert.equal(await eng.ready, true);
  await eng.play();
  const buffer = ctx.sources.find(s => s.started).buffer;
  for (let ch = 0; ch < channels; ch++) {
    for (let frame = 0; frame < frames; frame++) {
      assert.equal(buffer.getChannelData(ch)[frame], values[(frame * channels + ch) % values.length] / 8388608);
    }
  }
  eng.destroy();
}
console.log("PASS: PCM24 mono and multichannel interleaving");

for (const create of [createChunkedAudioEngine, createAudioEngine]) {
  for (const failure of ["missing", "unsupported"]) {
    files.set("/unsupported.wav", wav(32, 99));
    const eng = create([stems[0], { name: "lead_vocals", url: `/${failure}.wav` }], { context: new Context() });
    assert.equal(await eng.ready, false, `${create.name} must reject a partially loaded mix (${failure})`);
    assert.ok(eng.getLoadError());
    eng.destroy();
  }
}
console.log("PASS: neither engine silently accepts missing or unreadable playback lanes");
{
  const eng = createAudioEngine([stems[0], { name: "original", url: "/missing.wav", visualOnly: true }], { context: new Context() });
  assert.equal(await eng.ready, true, "optional waveform failure must not disable complete audible playback");
  eng.destroy();
}
console.log("PASS: visual-only decode failure does not disable audio");

for (const create of [createChunkedAudioEngine, createAudioEngine]) {
  // A visible lane can be reconstructed from multiple physical playback stems
  // (original complement): one PAN command must affect all its sources.
  const ctx = new Context();
  const group = [
    { name: "guitar", controlName: "strings", url: "/guitar.wav" },
    { name: "piano", controlName: "strings", url: "/piano.wav" },
    { name: "bass", url: "/bass.wav" },
  ];
  const eng = create(group, { context: ctx });
  assert.equal(await eng.ready, true);
  assert.equal(eng.supportsStereoPan(), true);
  assert.equal(ctx.panners.length, 3, "each audible source needs its own panner");
  assert.equal(eng.setStemPan("strings", -.65), true);
  assert.deepEqual(ctx.panners.map(p => p.pan.value), [-.65, -.65, 0],
    "PAN must not leak to another lane or pitch bus");
  assert.equal(eng.setStemPan("bass", .4), true);
  assert.deepEqual(ctx.panners.map(p => p.pan.value), [-.65, -.65, .4]);
  assert.equal(eng.setStemPan("bass", Number.NaN), true);
  assert.equal(ctx.panners[2].pan.value, 0, "non-finite pan must center safely");
  assert.equal(eng.setStemPan("missing", 1), false);
  eng.destroy();
}
console.log("PASS: grouped lanes pan independently in both Web Audio engines");

// Do not reject valid old browsers. Engines retain stereo playback without
// pan support and declare the control unavailable to the mixer.
for (const create of [createChunkedAudioEngine, createAudioEngine]) {
  const ctx = new Context();
  ctx.createStereoPanner = undefined;
  const eng = create([stems[0]], { context: ctx });
  assert.equal(await eng.ready, true);
  assert.equal(eng.supportsStereoPan(), false);
  assert.equal(eng.setStemPan("bass", -.9), false);
  eng.destroy();
}
console.log("PASS: older Web Audio contexts keep playback without PAN support");
