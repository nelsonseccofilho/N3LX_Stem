import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { editedLyrics, lyricsEditorText, untimedLines } from "../../static/js/lyricsEditing.js";
import { timingOf } from "../../static/js/lyricsSync.js";

const old = { synced: "[00:01.00] <00:01.00>Old <00:01.50>words\n[00:04.00] Next", offsetSec: 2 };
const corrected = editedLyrics(old, "New words\r\nNext");
assert.deepEqual(timingOf(corrected).lines.map((l) => [l.time, l.text]), [[3, "New words"], [6, "Next"]]);
assert.ok(!timingOf(corrected).lines[0].words, "changed words cannot retain old word stamps");
assert.equal(old.offsetSec, 2, "editing does not mutate the original/server entry");
const verses = editedLyrics(old, "Linha 1\r\n\r\nNovo verso");
assert.equal(lyricsEditorText(verses), "Linha 1\n\nNovo verso");
assert.equal(timingOf(verses).lines.length, 0, "a new verse cannot silently reuse unrelated timing");
const pasted = editedLyrics({}, "[00:02.00] Palavra\n[00:08.00] Outra");
assert.deepEqual(timingOf(pasted).lines.map((l) => l.time), [2, 8]);
const manual = untimedLines("Um\n\nDois", 12);
assert.deepEqual(manual.map((l) => l.text), ["Um", "", "Dois"]);
assert.equal(verses.synced, "", "opening manual timing does not fabricate persisted stamps");

const source = readFileSync(new URL("../../static/js/karaoke.js", import.meta.url), "utf8")
  .replace(/^import .*;\r?\n/gm, "").replace(/export /g, "");
const context = vm.createContext({});
vm.runInContext(source, context);
const combined = context.overviewPeaks({ vocals: [[0, 0], [0, 0]], drums: [[-1, 1], [0, 0]] }, 2);
assert.ok(combined[0] > 0, "the overview includes instruments even while vocals are silent");
assert.equal(combined[1], 0);
assert.equal(context.overviewPeaks({}).length, 0);
assert.ok(context.overviewPeaks({ bass: [[-.2, .2]] }, 8).every(Number.isFinite));
console.log("Karaoke: edits preserve line breaks and valid timing; no invented synchronization; overview covers all stems.");
