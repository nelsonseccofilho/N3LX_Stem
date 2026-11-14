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
  extract("function showAnswer({ song, matches })", "\n/**\n * The lyrics the server found"),
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
    production + "\nglobalThis.__run = loadForCurrentTrack; globalThis.__answer = showAnswer;",
    context,
  );
  return {
    run: () => context.__run(),
    answer: (answer) => context.__answer(answer),
    count: (event) => events.filter(([name]) => name === event).length,
  };
}

test("missing local lyrics start one automatic lookup", async () => {
  const h = harness();
  await h.run();
  assert.equal(h.count("lookup"), 1);
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

test("cached empty search keeps retry without repeated auto-search", async () => {
  const h = harness({ cached: { song: "Song", matches: [] } });
  await h.run();
  assert.equal(h.count("lookup"), 0);
  assert.equal(h.count("retry"), 1);
});

test("empty search shows retry; available alternatives remain offered", () => {
  const empty = harness();
  empty.answer({ song: "Song", matches: [] });
  assert.equal(empty.count("retry"), 1);
  const matches = harness();
  matches.answer({ song: "Song", matches: [{ id: 1 }] });
  assert.equal(matches.count("offer"), 1);
  assert.equal(matches.count("retry"), 0);
});
