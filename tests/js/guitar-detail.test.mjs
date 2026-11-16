import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

function moduleSource(file) {
  return fs.readFileSync(new URL(`../../static/js/${file}`, import.meta.url), "utf8")
    .replace(/^import[^;]+;\r?\n/gm, "").replace(/^export /gm, "");
}
const names = ["guitar_lead", "guitar_acoustic", "guitar_rhythm", "residual_guitar"];
const stored = new Map();
const context = vm.createContext({
  console, structuredClone, currentJobId:"song", TRACK_NAMES:["bass","guitar"], EXTRA_STEM_NAMES:names,
  STEM_NAMES:["bass","guitar"], mixerState:{},
  storeGet:async(key, fallback)=>stored.get(key) || fallback,
  storeSetDebounced:(key,value)=>stored.set(key,structuredClone(value)), flushStoreWrites:async()=>{},
});
vm.runInContext(moduleSource("mixer.js") + "\nglobalThis.api={loadMixIntoState,prepareGuitarMix,getMixerReloadContext};", context);
const guitar = {volume:.36, muted:true, soloed:false, pitch:3};
const playlist = {mix:{guitar, bass:{volume:.8}}, save(value){this.saved=value;}};
await context.api.loadMixIntoState("song", names, playlist);
for (const name of names) assert.deepEqual({...context.mixerState[name]}, guitar);
context.mixerState.guitar_lead.volume = .14;
playlist.mix = {guitar:{volume:.99}}; // The old context's initial mix can be stale.
const reload = context.api.getMixerReloadContext("song");
assert.equal(reload.mix.guitar_lead.volume,.14);
assert.equal(reload.mix.guitar.volume,.36);
assert.equal(context.api.getMixerReloadContext("other-song"),null);
await context.api.prepareGuitarMix("song",names);
for (const name of names) assert.deepEqual({...context.mixerState[name]},guitar);
assert.equal(stored.size,0,"playlist edits must not overwrite the library mix");
await context.api.loadMixIntoState("song",names,{mix:{guitar:{muted:false,volume:.8},guitar_lead:{volume:.2}},save(){}});
assert.equal(context.mixerState.guitar_lead.volume,.2,"explicit per-lane settings win over inherited values");
assert.equal(context.mixerState.guitar_acoustic.volume,.8);
assert.equal(context.mixerState.guitar_acoustic.muted,false);
let untouchedPlaylist;
await context.api.loadMixIntoState("song",["bass","guitar"],{mix:{guitar},save(value){untouchedPlaylist=value;}});
assert.equal(untouchedPlaylist.guitar_lead,undefined,"opening the original must not create fake explicit guitar settings");

const playback = vm.createContext({DRUM_STEMS:[], isPercussion:()=>false});
vm.runInContext(moduleSource("playbackStems.js")+"\nglobalThis.build=buildPlaybackStems",playback);
const stem = name=>({name,url:`/${name}.wav`});
const result = playback.build(["original","guitar","bass",...names].map(stem),["original",...names].map(stem),["guitar","bass"]);
assert.equal(result.filter(s=>s.name==="guitar").length,0,"original guitar must not play twice");
assert.equal(result.find(s=>s.name==="bass").controlName,"original");

const progress = vm.createContext({t:key=>key});
vm.runInContext(moduleSource("guitarDetail.js")+"\nglobalThis.progress=guitarProgress",progress);
assert.match(progress.progress({status:"running",elapsed:65,progress:{role:"lead",chunk:2,chunks:12,phase:"generate"}}),/1:05/);
assert.equal(progress.progress({status:"cancelling"}),"guitar.status.cancelling");
assert.equal(progress.progress({status:"cancelled"}),"guitar.status.cancelled");
console.log("Guitar detail: independent playlist mixes, original controls inherited, no duplicate source, real progress: passed");
