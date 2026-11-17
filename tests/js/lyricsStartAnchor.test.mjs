import assert from "node:assert/strict";
import { parseLyricClock, anchorFirstSungLine } from "../../static/js/lyricsStartAnchor.js";

assert.equal(parseLyricClock("00:22", 245), 22);
assert.equal(parseLyricClock("1:05.25", 245), 65.25);
assert.equal(parseLyricClock("22", 245), 22);
for (const bad of ["01:66", "-1", "00:22foo", "NaN", "04:10"]) {
  assert.equal(parseLyricClock(bad, 245), null, bad);
}
const original = [
  { time: 17.8, text: "A rua respira sal, um vidro guarda luz,", words: [
    { time: 17.8, text: "A " }, { time: 18.1, text: "rua " }, { time: 20.1, text: "luz," },
  ] },
  { time: 20.8, text: "" },
  { time: 28.0, text: "um gesto que ficou no canto do espelho." },
];
const fixed = anchorFirstSungLine(original, 22, 245);
assert.equal(fixed.index, 0);
assert.equal(fixed.lines[0].time, 22);
assert.equal(fixed.lines[0].text, original[0].text);
assert.equal(fixed.lines[1].text, "");
assert.ok(fixed.lines[1].time > 22.1, "The pause marker must not immediately hide the first phrase");
assert.equal(fixed.lines[2].time, 28, "Already timed later phrases should not shift");
assert.equal(original[0].time, 17.8, "Must not mutate saved input");
assert.equal(original[1].time, 20.8, "Must not mutate original pause marker");
assert.equal(anchorFirstSungLine([], 22, 245), null);
console.log("lyricsStartAnchor: PASS");
