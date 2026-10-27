import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { karaokePreviewFromTiming, hasProtectedLyrics } from "../../static/js/karaokeTiming.js";

const timing = {
  v: 1, engine: "whisper.cpp", timing_status: "machine_unverified",
  words: [
    { text: "Eu", start: 0.14, end: 0.31 },
    { text: "vou", start: 0.33, end: 0.50 },
    { text: "cantar", start: 0.53, end: 1.11 },
    { text: "agora", start: 2.10, end: 2.65 },
  ],
};
const preview = karaokePreviewFromTiming(timing, { title: "Canção", artist: "N3LX", duration: 8 });
assert.ok(preview);
assert.equal(preview.source, "whisper");
assert.equal(preview.machinePreview, true);
assert.equal(preview.timingStatus, "machine_unverified");
assert.equal(preview.synced,
  "[00:00.14]<00:00.14>Eu <00:00.33>vou <00:00.53>cantar<00:01.11>\n" +
  "[00:02.10]<00:02.10>agora<00:02.65>");
assert.equal(preview.plain, "Eu vou cantar\nagora");
assert.equal(preview.track, "Canção");
assert.equal(preview.duration, 8);
assert.equal(timing.words[0].text, "Eu", "JSON is never mutated");

for (const bad of [
  null, {}, { v: 2, words: timing.words },
  { v: 1, words: timing.words.slice(0, 2) },
  { v: 1, words: [timing.words[0], { text: "x", start: NaN, end: 1 }, timing.words[2]] },
  { v: 1, words: [timing.words[0], { text: "x", start: 10, end: 10.1 }, timing.words[2]] },
  { v: 1, words: [timing.words[0], { text: "<script>", start: .4, end: .5 }, timing.words[2]] },
  { v: 1, words: [timing.words[0], { text: "x", start: .3, end: -.1 }, timing.words[2]] },
]) {
  assert.equal(karaokePreviewFromTiming(bad), null, "invalid input must never render");
}
assert.equal(hasProtectedLyrics({ source: "manual" }), true);
assert.equal(hasProtectedLyrics({ userSynced: "[00:01.00] Olá" }), true);
assert.equal(hasProtectedLyrics({}, true), true, "active editor protects work in progress");
assert.equal(hasProtectedLyrics({ source: "lrclib", synced: "" }), false);

const html = readFileSync(new URL("../../static/index.html", import.meta.url), "utf8");
for (const id of ["lyricsGenerateKaraokeBtn", "lyricsCancelKaraokeBtn", "lyricsRegenerateKaraokeBtn", "lyricsTimingJsonLink", "lyricsAdvanced"]) {
  assert.equal((html.match(new RegExp(`id="${id}"`, "g")) || []).length, 1, `single ${id} control`);
}
const lyrics = readFileSync(new URL("../../static/js/lyrics.js", import.meta.url), "utf8");
assert.ok(lyrics.includes('fetch(karaokeApi(trackId, "generate")'), "UI actually calls the generation endpoint");
assert.ok(lyrics.includes('fetch(karaokeApi(trackId, "timing")'), "UI reads stored word timecodes");
assert.ok(lyrics.includes('fetch(karaokeApi(trackId, "cancel")'), "UI supports cancellation");
assert.ok(lyrics.includes('if (from !== "preview") tools.append(remove);'), "preview is not exposed to destructive removal");
console.log("Karaoke timing UI: generated preview, safety, manual precedence and control wiring PASS");
