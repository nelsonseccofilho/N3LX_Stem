import assert from "node:assert/strict";
import { createSetlistPlayer } from "../../static/js/setlistPlayer.js";
import { normalizeSetlists, newPlaylist, applyMixToPlaylist, copyMix } from "../../static/js/setlistLibrary.js";
import { clampStereoPan, panLabel } from "../../static/js/stereoPan.js";
const calls = [];
const player = createSetlistPlayer({ open: async id => calls.push(`open:${id}`), play: async () => { calls.push("play"); return true; }, stop: () => calls.push("stop") });
player.setItems(["one", "two"]);
assert(await player.start());
assert.deepEqual(calls, ["stop", "open:one", "play"]);
assert.equal(player.state().status, "playing");
player.transport("pause"); await player.ended("one"); assert.equal(player.state().index, 0);
player.transport("play");
const transition = player.ended("one");
await player.ended("one"); await transition;
assert.equal(player.state().currentId, "two");
assert.equal(calls.filter(c => c === "open:two").length, 1);
await player.ended("two"); assert.equal(player.state().status, "completed");
await player.ended("two"); assert.equal(calls.filter(c => c === "play").length, 2);
let release;
const loading = createSetlistPlayer({ open: () => new Promise(resolve => release = resolve), play: async () => { throw new Error("must not play after cancellation"); }, stop: () => {} });
loading.setItems(["one", "two"]); const start = loading.start(); loading.cancel(); release();
assert.equal(await start, false); assert.equal(loading.state().status, "idle");
const failed = createSetlistPlayer({ open: async () => { throw new Error("missing file"); }, play: async () => true, stop: () => {} });
failed.setItems(["missing", "two"]); assert.equal(await failed.start(), false);
assert.equal(failed.state().status, "error"); assert.equal(failed.state().index, 0);
assert(player.setItems(["two", "one"])); assert(await player.start());
assert.equal(player.setItems(["one"]), false); player.cancel();
const original = newPlaylist("p1", "Bass off"); original.entries = [{id:"one", mix:{bass:{volume:0.75,muted:true}}}]; original.metro = {enabled:true,countInBars:2};
const copy = newPlaylist("p2", "Guitar off", original);
copy.entries[0].mix.bass.muted = false; copy.metro.countInBars = 0;
assert.equal(original.entries[0].mix.bass.muted, true); assert.equal(original.metro.countInBars, 2);
copy.entries.push({id:"two",mix:{}}); applyMixToPlaylist(copy, {guitar:{volume:1,muted:true},lead_vocals:{volume:0.5,muted:true}});
assert(copy.entries.every(e => e.mix.guitar.muted && e.mix.lead_vocals.muted));
copy.entries[0].mix.guitar.volume=0.2; assert.equal(copy.entries[1].mix.guitar.volume,1);
assert.equal(original.entries[0].mix.bass.volume,0.75);
const restored = normalizeSetlists({selectedId:"p2",playlists:[original,copy]},()=>"new");
assert.equal(restored.selectedId,"p2"); assert.equal(restored.playlists[0].entries[0].mix.bass.muted,true);
const empty = normalizeSetlists({playlists:[{id:"bad/path"},{id:"ok",entries:{invalid:true}}]},()=>"new");
assert.equal(empty.playlists.length,1); assert.deepEqual(empty.playlists[0].entries,[]);
console.log("Setlist sequencing, pause, cancellation, failure, duplicate end events and isolated playlist mixes: passed");

let resolveOldPlay;
let playCalls=0;
const raced = createSetlistPlayer({ open: async () => {}, play: () => ++playCalls === 1 ? new Promise(resolve => resolveOldPlay=resolve) : Promise.resolve(true), stop: () => {} });
raced.setItems(["one", "two"]);
const first = raced.start(0); await Promise.resolve(); await Promise.resolve();
await raced.start(1); resolveOldPlay(true); await first;
assert.equal(raced.state().currentId,"two"); assert.equal(raced.state().status,"playing");
raced.cancel();
console.log("A stale start cannot stop or overwrite the next song: passed");

assert(await player.start(0)); player.fail("audio lost");
assert.equal(player.state().status,"error"); await player.ended("one"); assert.equal(player.state().index,0);
assert.deepEqual(normalizeSetlists({playlists:[{id:"p",entries:[null,{id:"valid",mix:{}}]}]},()=>"new").playlists[0].entries.map(e=>e.id),["valid"]);
console.log("Runtime playback errors stop the sequence and damaged entries recover safely: passed");

assert.equal(copyMix({guitar:{volume:1,pan:-.72}}).guitar.pan, -.72,
  "PAN must survive playlist copy");
assert.equal(copyMix({guitar:{volume:1}}).guitar.pan, 0,
  "old playlists must default to center");
assert.equal(copyMix({guitar:{pan:5}}).guitar.pan, 1,
  "invalid out-of-range PAN must be capped");
assert.equal(copyMix({guitar:{pan:"oops"}}).guitar.pan, 0,
  "untrusted strings may not become PAN");
assert.equal(clampStereoPan(NaN), 0);
assert.equal(panLabel(-.5), "L50");
assert.equal(panLabel(0), "C");
assert.equal(panLabel(.6), "R60");
const stereoMix = newPlaylist("stereo", "Stereo");
stereoMix.entries = [{id:"one",mix:{guitar:{pan:-.8}}}, {id:"two",mix:{guitar:{pan:.5}}}];
const stereoCopy = newPlaylist("stereo-copy","Stereo Copy",stereoMix);
assert.equal(stereoCopy.entries[0].mix.guitar.pan,-.8);
stereoCopy.entries[0].mix.guitar.pan = .25;
assert.equal(stereoMix.entries[0].mix.guitar.pan,-.8,
  "duplicating a playlist must not alias mix state");
applyMixToPlaylist(stereoCopy, {guitar:{pan:.4}});
assert(stereoCopy.entries.every(entry=>entry.mix.guitar.pan === .4));
console.log("PASS: stereo PAN persists independently across library and playlist mixes");
