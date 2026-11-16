// Guard the behavior of the Lyrics tab without starting the backend,
// external LRCLIB requests, Electron, music imports, or user library access.
// Run: node --test tests/js/lyrics-auto-lookup-rc10.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../../static/js/lyrics.js", import.meta.url), "utf8");
function extract(start, end) {
  const from = source.indexOf(start);
  assert.ok(from >= 0, "Missing production function: " + start);
  const to = source.indexOf(end, from);
  assert.ok(to > from, "Missing source boundary for: " + start);
  return source.slice(from, to);
}
const production = [
  extract("async function loadForCurrentTrack()", "\n// While the tab is on screen"),
].join("\n");

function harness({ saved = null, timing = null, server = null, embedded = "", song = "Song", cached = null } = {}) {
  const events = [];
  const track = {
    id: "fixture-track", title: "Song", duration: 95,
    audioTags: { title: "Song", artist: "Band", lyrics: embedded },
  };
  const context = vm.createContext({
    shownTrackId: null, alignOpen: false, syncOpen: false, sync: null,
    nothingKnownFor: null, searchController: null, loadToken: 0,
    shownEntry: null, answered: new Map(cached ? [[track.id, cached]] : []),
    getCurrentTrackInfo: () => track,
    selectKaraokeTrack: () => {},
    clearLyrics: () => {},
    getCurrentTrackArtist: () => ({ name: "Band" }),
    setStatus: (message) => events.push(["status", message]),
    t: (key) => key,
    storeGet: async () => saved,
    storeSet: async () => {},
    storeKey: (id) => "lyrics:" + id,
    timingOf: () => ({ lines: [{ time: 1, text: "Manual lyric" }] }),
    keptForAnotherSong: () => false,
    show: (entry) => events.push(["show", entry.source]),
    karaokeApi: (id, action) => "/test/" + id + "/" + action,
    fetch: async (url) => {
      assert.match(url, /\/timing$/);
      return { ok: !!timing, status: timing ? 200 : 404, json: async () => timing };
    },
    previewKaraoke: () => events.push(["preview"]),
    setKaraokeMessage: (key) => events.push(["karaoke-message", key]),
    serverLyrics: async () => server,
    offer: (options) => events.push(["offer", options.length]),
    embeddedLyrics: async () => embedded,
    knownSong: () => ({ artist: "Band", song, names: [] }),
    parseLrc: () => [],
    keep: async () => events.push(["keep"]),
    document: { getElementById: () => null },
    versionsEl: {
      append: (value) => events.push(["append", value]),
      replaceChildren: (value) => events.push(["retry", value]),
    },
    lookAgainButton: () => "retry-button",
    lookUp: async (_info, args) => events.push(["lookup", args.song]),
  });
  vm.runInContext(
    production + "\nglobalThis.__run = loadForCurrentTrack;",
    context,
  );
  return {
    run: () => context.__run(),
    count: (event) => events.filter(([name]) => name === event).length,
  };
}

test("opening an empty track never queries LRCLIB automatically", async () => {
  const h = harness();
  await h.run();
  assert.equal(h.count("lookup"), 0);
  assert.equal(h.count("append"), 0);
});

test("manual lyrics are shown without external search", async () => {
  const h = harness({ saved: { entry: { source: "manual", plain: "Edited lyrics" } } });
  await h.run();
  assert.equal(h.count("show"), 1);
  assert.equal(h.count("lookup"), 0);
});

test("karaoke sidecar is used without external search", async () => {
  const h = harness({ timing: { words: [{ text: "Song", start: 1, end: 2 }] } });
  await h.run();
  assert.equal(h.count("preview"), 1);
  assert.equal(h.count("lookup"), 0);
});

test("server lyrics do not trigger duplicate lookup", async () => {
  const h = harness({ server: { entry: { source: "lrclib", plain: "Found" }, others: [] } });
  await h.run();
  assert.equal(h.count("show"), 1);
  assert.equal(h.count("lookup"), 0);
});

test("embedded lyrics are kept without external search", async () => {
  const h = harness({ embedded: "Lyrics from file" });
  await h.run();
  assert.equal(h.count("keep"), 1);
  assert.equal(h.count("lookup"), 0);
});

test("unknown song is not sent to lookup", async () => {
  const h = harness({ song: "" });
  await h.run();
  assert.equal(h.count("lookup"), 0);
});

test("a previous empty answer also never triggers auto-search", async () => {
  const h = harness({ cached: { song: "Song", matches: [] } });
  await h.run();
  assert.equal(h.count("lookup"), 0);
  assert.equal(h.count("retry"), 0);
});

const submitSource = extract(
  "async function submitManualLyricsSearch(event)",
  "\nasync function serverLyrics(trackId)",
);

test("explicit search requires a button/form submission and never saves a match", async () => {
  const requests = [];
  const selected = [];
  const closed = [];
  const fields = {
    lyricsSearchArtist: { value: "CPM 22" },
    lyricsSearchTitle: { value: "Não Sei Viver Sem Ter Você" },
    lyricsSearchStatus: { textContent: "" },
    lyricsSearchSubmitBtn: { disabled: false },
    lyricsSearchForm: { hidden: false },
    lyricsOpenSearchBtn: { setAttribute: () => {} },
    karaokeSettings: { close: () => closed.push(true) },
  };
  const context = vm.createContext({
    searchController: null, karaokeRunning: false, karaokeDeleting: false,
    AbortController, getCurrentTrackInfo: () => ({ id: "fixture-track" }),
    document: { getElementById: (id) => fields[id] || null },
    t: (key) => key,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, status: 200, json: async () => ({ others: [{ id: 4 }] }) };
    },
    fromServerLyrics: (value) => ({ others: value.others }),
    showManualLookupChoices: (matches) => selected.push(matches),
    console,
  });
  vm.runInContext(
    submitSource + "\nglobalThis.__submit = submitManualLyricsSearch;",
    context,
  );
  assert.equal(requests.length, 0);
  await context.__submit({ preventDefault: () => {} });
  assert.equal(requests.length, 1);
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    artist: "CPM 22", title: "Não Sei Viver Sem Ter Você",
  });
  assert.equal(selected.length, 1);
  assert.equal(fields.lyricsSearchForm.hidden, false);
  assert.equal(closed.length, 0); // Search must not close the modal.
});

test("manual search refuses an empty artist and does not contact LRCLIB", async () => {
  let requests = 0;
  const fields = {
    lyricsSearchArtist: { value: "" },
    lyricsSearchTitle: { value: "Song" },
    lyricsSearchStatus: { textContent: "" },
    lyricsSearchSubmitBtn: { disabled: false },
  };
  const context = vm.createContext({
    searchController: null, karaokeRunning: false, karaokeDeleting: false,
    AbortController, getCurrentTrackInfo: () => ({ id: "fixture-track" }),
    document: { getElementById: (id) => fields[id] || null },
    t: (key) => key,
    fetch: async () => { requests++; },
  });
  vm.runInContext(
    submitSource + "\nglobalThis.__submit = submitManualLyricsSearch;",
    context,
  );
  await context.__submit({ preventDefault: () => {} });
  assert.equal(requests, 0);
});
test("a failed search stays visible inside the modal without clearing lyrics", async () => {
  const fields = {
    lyricsSearchArtist: { value: "CPM 22" },
    lyricsSearchTitle: { value: "Não Sei Viver Sem Ter Você Ao Vivo" },
    lyricsSearchStatus: { textContent: "", setAttribute: () => {} },
    lyricsSearchSubmitBtn: { disabled: false },
    lyricsSearchResults: { hidden: true, replaceChildren: () => {} },
  };
  const context = vm.createContext({
    searchController: null, karaokeRunning: false, karaokeDeleting: false,
    AbortController, getCurrentTrackInfo: () => ({ id: "fixture-track" }),
    document: { getElementById: (id) => fields[id] || null },
    t: (key) => key,
    fetch: async () => ({ ok: false, status: 404, json: async () => ({ others: [] }) }),
    fromServerLyrics: (value) => ({ others: value.others }),
    console,
  });
  vm.runInContext(submitSource + "\nglobalThis.__submit = submitManualLyricsSearch;", context);
  await context.__submit({ preventDefault: () => {} });
  assert.equal(fields.lyricsSearchStatus.textContent, "lyrics.searchNoResults");
});

const manualChoicesSource = extract(
  "function showManualLookupChoices(matches)",
  "\nasync function submitManualLyricsSearch(event)",
);

test("manual options render inside settings without replacing the visible lyric", () => {
  let renders = 0;
  const results = { hidden: true, replaceChildren: (...items) => { renders = items.length; } };
  const context = vm.createContext({
    getCurrentTrackInfo: () => ({ id: "fixture-track", duration: 234 }),
    document: { getElementById: (id) => id === "lyricsSearchResults" ? results : null },
    versionList: () => ({}),
    el: (_tag, _className, text) => ({ text }),
    t: (key) => key,
  });
  vm.runInContext(manualChoicesSource + "\nglobalThis.__show = showManualLookupChoices;", context);
  context.__show([{ lrclib_id: 91 }, { lrclib_id: 92 }]);
  assert.equal(results.hidden, false);
  assert.equal(renders, 2);
});
