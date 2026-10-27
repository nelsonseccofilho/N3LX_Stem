// Exercise the real catalog selection/completion functions with deterministic
// network and audio adapters. No extraction or user-library writes are needed.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const calls = [];
const snapshots = new Map();
let flush = () => Promise.resolve();
let queue = { running: null, queued: [] };
const text = () => ({ textContent: "", classList: { add() {}, remove() {} } });
const context = vm.createContext({
  console, URL, setTimeout, clearTimeout, setInterval, clearInterval,
  crypto: { randomUUID: () => "qa-collection" },
  CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
  document: { dispatchEvent() {}, querySelector: () => null, querySelectorAll: () => [], getElementById: () => null },
  window: { addEventListener() {} },
  onLanguageChange() {}, i18nT: key => key,
  PROCESSING_STATUSES: new Set(["queued", "downloading", "analyzing", "separating", "processing"]),
  audioEngine: null, multitrack: null, foregroundJobId: null, processingActiveId: null,
  titleEl: text(), bpmChip: text(), keyChip: text(), selectedStems: new Set(),
  detachForegroundJob() { context.foregroundJobId = null; },
  destroyPlayer() { calls.push("destroy"); context.audioEngine = context.multitrack = null; context.processingActiveId = null; },
  renderEmptyShell() { calls.push("empty"); },
  setCurrentJobId(id) { calls.push(`job:${id}`); },
  showProcessingStudio(job) { calls.push(`processing:${job.job_id}`); context.processingActiveId = job.job_id; },
  isProcessingStudio: id => context.processingActiveId === id,
  updateProcessingStudio(job) { calls.push(`progress:${job.job_id}:${job.status}`); },
  getQueueSnapshot: () => queue,
  flushStoreWrites: () => flush(),
  wireUpAudio(id) { calls.push(`audio:${id}`); context.audioEngine = {}; context.processingActiveId = null; },
  initSections() {}, isReimportableSource: () => false,
  runVocalSplitIfWanted: async state => state,
  fetch: async url => ({ ok: true, json: async () => url.endsWith("/peaks") ? {} : snapshots.get(url.split("/").at(-1)) }),
});
const source = fs.readFileSync(new URL("../../static/js/catalog.js", import.meta.url), "utf8")
  .replace(/^import[\s\S]*?;\r?\n/gm, "")
  .replace(/^export /gm, "");
vm.runInContext(source + `
  render = () => {};
  saveState = () => Promise.resolve();
  applyTrackInfoToPanel = track => { titleEl.textContent = track.title; };
  applyStoredStemSelection = () => {};
  backfillAudioTags = () => {};
  addTrackToLibrary = track => { tracks[track.id] = { ...tracks[track.id], ...track }; };
  globalThis.testCatalog = {
    armAutoOpen, loadTrackIntoStudio, completeSettledJob, isLibraryTrack, libraryFolderItems, queueEntries, setCatalogView, selectQueuedTrack, reorderFolderTrack, organizeSong,
    folderSeed: value => { folders = value; },
    view: () => catalogView,
    entries: () => queueEntries(getQueueSnapshot()).map(({job}) => job.job_id),
    selected: () => _currentTrackId,
    seed: value => { tracks = value; folders = []; _currentTrackId = null; _loadTrackToken++; _autoOpenTokens.clear(); }
  };`, context);
const catalog = context.testCatalog;
function track(id, status = "done") {
  const result = { id, job_id: id, title: id, status, audioStems: [{ name: "bass", url: `/${id}.wav` }], sourceUrl: `local:${id}` };
  snapshots.set(id, { ...result, stems: result.audioStems });
  return result;
}
function seed() {
  calls.length = 0;
  queue = {running:null,queued:[]};
  context.audioEngine = {}; context.multitrack = null; context.processingActiveId = null;
  catalog.seed({ old: track("old"), next: track("next"), pending: track("pending", "separating"), queued: track("queued", "queued") });
}

seed();
catalog.armAutoOpen("pending", { activate: true });
assert.equal(catalog.selected(), "pending");
assert.equal(catalog.view(), "queue", "accepting extraction opens the queue");
assert.deepEqual([...catalog.entries()], ["pending"], "accepted import appears before the next queue frame");
assert.equal(catalog.isLibraryTrack(track("pending", "separating")), false);
assert.deepEqual([...catalog.libraryFolderItems({items:["old", "pending", "queued", "next"]})], ["old", "next"]);
for (const status of ["queued", "downloading", "analyzing", "separating", "processing", "error", "cancelled", "stopped"]) {
  assert.equal(catalog.isLibraryTrack({status}), false, `${status} is not a finished library result`);
}
assert(catalog.isLibraryTrack({status:"done"}));
assert(catalog.isLibraryTrack({status:"unavailable"}), "previously extracted missing audio stays restorable");
assert(catalog.isLibraryTrack({audioStems:[{name:"bass"}]}), "legacy extracted tracks stay visible");
assert.equal(context.audioEngine, null);
assert.deepEqual(calls.slice(0, 4), ["destroy", "empty", "job:pending", "processing:pending"]);
await catalog.loadTrackIntoStudio("next");
assert.equal(catalog.selected(), "next");
snapshots.set("pending", { ...snapshots.get("pending"), status: "done" });
await catalog.completeSettledJob("pending");
assert.equal(catalog.selected(), "next");
assert(!calls.includes("audio:pending"), "completion must not interrupt another ready song");
assert.equal(catalog.view(), "library", "the empty queue opens the library after final metadata arrives");
assert(!catalog.entries().includes("pending"));

seed();
catalog.armAutoOpen("pending", { activate:true });
catalog.setCatalogView("library");
catalog.armAutoOpen("queued");
assert.equal(catalog.view(), "library", "later batch files must not navigate back to the queue");
snapshots.set("pending", {...snapshots.get("pending"),status:"done"});
await catalog.completeSettledJob("pending");
await new Promise(resolve => setImmediate(resolve));
assert.equal(catalog.view(), "library", "completion respects a manual library selection");
assert.deepEqual([...catalog.libraryFolderItems({items:["old", "pending", "queued", "next"]})], ["old", "pending", "next"]);
queue = {running:snapshots.get("queued"),queued:[]};
assert.equal(catalog.entries().filter(id => id==="queued").length,1,"shared queue frames replace optimistic entries without duplicates");
queue = {running:null,queued:[]};
console.log("Queue navigation, completed-only library visibility, folder counts and optimistic queue entries: passed");

seed();
catalog.armAutoOpen("pending", { activate: true });
let release;
flush = () => new Promise(resolve => { release = resolve; });
const opening = catalog.loadTrackIntoStudio("next");
snapshots.set("pending", { ...snapshots.get("pending"), status: "done" });
await catalog.completeSettledJob("pending");
assert(!calls.includes("audio:pending"), "a ready song still loading already owns the studio");
release(); flush = () => Promise.resolve(); await opening;
assert.equal(catalog.selected(), "next");

seed();
catalog.armAutoOpen("pending", { activate: true });
catalog.armAutoOpen("queued");
snapshots.set("queued", { ...snapshots.get("queued"), status: "done" });
await catalog.completeSettledJob("queued");
assert.equal(catalog.selected(), "pending", "another batch completion must not replace the selected extraction");
snapshots.set("pending", { ...snapshots.get("pending"), status: "done" });
await catalog.completeSettledJob("pending");
await new Promise(resolve => setImmediate(resolve));
assert.equal(catalog.selected(), "pending");
assert(calls.includes("audio:pending"), "selected extraction opens its finished audio");

seed();
await catalog.loadTrackIntoStudio("queued");
assert.equal(catalog.selected(), "queued");
assert(calls.includes("processing:queued"), "queued rows can be reopened while processing");
assert(!calls.includes("audio:queued"), "old stems on a queued track must not play");
snapshots.set("queued", { ...snapshots.get("queued"), status: "error", error: "fixture failure" });
context.notifyFailure = () => {};
await catalog.completeSettledJob("queued");
assert(calls.includes("progress:queued:error"));
assert(!calls.includes("audio:queued"));
console.log("Processing selection: active empty studio, ready-track navigation, load races, batch ownership, completion and failure passed");

seed();
queue = {running:snapshots.get("pending"),queued:[snapshots.get("queued")]};
await catalog.loadTrackIntoStudio("old");
assert.equal(catalog.selected(), "old");
catalog.setCatalogView("queue");
assert.equal(catalog.selected(), "pending", "entering Queue replaces the previous song with its running extraction");
assert.equal(context.audioEngine, null);
assert.equal(context.processingActiveId, "pending");
const destroys = calls.filter(call => call === "destroy").length;
catalog.setCatalogView("queue");
assert.equal(calls.filter(call => call === "destroy").length, destroys, "opening the same queue item is idempotent");
catalog.selectQueuedTrack("queued");
assert.equal(catalog.selected(), "queued");
catalog.setCatalogView("queue");
assert.equal(catalog.selected(), "queued", "returning to Queue preserves the chosen queued item");
catalog.setCatalogView("library");
await catalog.loadTrackIntoStudio("next");
assert.equal(catalog.selected(), "next");
assert(context.audioEngine, "the library can still open a ready song after viewing Queue");

seed();
queue = {running:{job_id:"external",title:"Imported elsewhere",status:"separating"},queued:[]};
catalog.setCatalogView("queue");
assert.equal(catalog.selected(), "external", "queue items submitted by another client are selectable");
assert.equal(context.processingActiveId, "external");
assert.equal(catalog.libraryFolderItems({items:["external"]}).length,0);
queue = {running:null,queued:[]};
console.log("Queue entry clears the previous song, preserves explicit row selection and adopts external jobs: passed");

// The legacy foreground restore may await a vocal split or layout refresh.
// Switching songs during that await must invalidate its eventual audio mount.
let selectionChanged;
let resolveLayout;
let mounted = 0;
const foreground = vm.createContext({
  console, setTimeout, clearTimeout, setInterval, clearInterval,
  document: { addEventListener(name, fn) { if (name === "trackwillopen") selectionChanged = fn; } },
  window: { addEventListener() {} },
  fetch: () => new Promise(resolve => { resolveLayout = resolve; }),
  wireUpAudio: () => { mounted++; }, initSections() {}, paintFinishedTrackNames() {},
});
const jobSource = fs.readFileSync(new URL("../../static/js/job.js", import.meta.url), "utf8")
  .replace(/^import[\s\S]*?;\r?\n/gm, "").replace(/^export /gm, "");
vm.runInContext(jobSource + "\nglobalThis.finish = finishDoneJob;", foreground);
const finalJob = { job_id: "restore", status: "done", separation_profile: "complete" };
const staleFinish = foreground.finish(finalJob);
await new Promise(resolve => setImmediate(resolve));
selectionChanged();
resolveLayout({ ok: true, json: async () => finalJob });
await staleFinish;
assert.equal(mounted, 0, "an old foreground restore cannot replace the selected song");
const ownFinish = foreground.finish(finalJob);
await new Promise(resolve => setImmediate(resolve));
resolveLayout({ ok: true, json: async () => finalJob });
await ownFinish;
assert.equal(mounted, 1, "the watched foreground restore still opens on completion");
console.log("Foreground completion also respects navigation during async layout refresh: passed");

const transportSource = fs.readFileSync(new URL("../../static/js/transport.js", import.meta.url), "utf8");
const timeStart = transportSource.indexOf("export function updateFooterTimes(");
const timeEnd = transportSource.indexOf("\n}", timeStart) + 2;
const clock = vm.createContext({ totalDuration: 0, footerTimeElapsed: { textContent: "01:23" },
  footerTimeTotal: { textContent: "04:56" }, npScrubFill: { style: {} }, footerWaveDrawFn: null,
  fmtTime: seconds => String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(Math.floor(seconds % 60)).padStart(2, "0"),
});
vm.runInContext(transportSource.slice(timeStart, timeEnd).replace("export ", "") + "\nupdateFooterTimes(0);", clock);
assert.equal(clock.footerTimeElapsed.textContent, "00:00");
assert.equal(clock.footerTimeTotal.textContent, "00:00");
assert.equal(clock.npScrubFill.style.width, "0%");
clock.totalDuration = 120;
vm.runInContext("updateFooterTimes(30)", clock);
assert.equal(clock.footerTimeElapsed.textContent, "00:30");
assert.equal(clock.footerTimeTotal.textContent, "02:00");
assert.equal(clock.npScrubFill.style.width, "25%");
console.log("The empty studio clears the old song's transport clock and seek progress: passed");

// Reordering finished songs must not discard a hidden pending import or touch
// another folder. Boundary/invalid moves are no-ops.
catalog.seed({ a: track("a"), b: track("b"), c: track("c"), pending: track("pending", "separating") });
const orderedFolder = { id:"album", items:["a","pending","b","c"] };
const anotherFolder = { id:"another", items:["c"] };
catalog.folderSeed([orderedFolder, anotherFolder]);
catalog.reorderFolderTrack("album","b",-1);
assert.deepEqual(orderedFolder.items,["b","pending","a","c"]);
catalog.reorderFolderTrack("album","b",-1);
catalog.reorderFolderTrack("album","pending",1);
catalog.reorderFolderTrack("album","a",8);
assert.deepEqual(orderedFolder.items,["b","pending","a","c"]);
catalog.reorderFolderTrack("album","a",1);
assert.deepEqual(orderedFolder.items,["b","pending","c","a"]);
assert.deepEqual(anotherFolder.items,["c"]);
console.log("Folder song order preserves pending imports, other folders and boundaries: passed");
await assert.rejects(catalog.organizeSong("a", "missing"));
assert(orderedFolder.items.includes("a"));
await catalog.organizeSong("a", "another");
assert(!orderedFolder.items.includes("a")); assert(anotherFolder.items.includes("a"));
await assert.rejects(catalog.organizeSong("pending", "another"));
await assert.rejects(catalog.organizeSong("b", null, "<invalid>"));
assert(orderedFolder.items.includes("b"));
assert.equal(await catalog.organizeSong("b", null, "Nova coleção"), "Nova coleção");
assert(!orderedFolder.items.includes("b"));
assert.deepEqual(anotherFolder.items,["c","a"]);
console.log("Song organization validates destinations/names and preserves other songs: passed");
