import { parseLrc } from "./lyricsLookup.js";
import { timingOf, serializeLrc } from "./lyricsSync.js";

export function lyricsEditorText(entry) {
  return entry?.plain || timingOf(entry).lines.map((line) => line.text).join("\n") || "";
}

// Keep line starts only when the edited lines still correspond one-to-one.
// Changed words lose their old word stamps. Added/removed lines need retiming.
export function editedLyrics(entry, text) {
  const plain = String(text).replace(/\r\n?/g, "\n").normalize("NFC");
  const supplied = parseLrc(plain);
  const previous = timingOf(entry).lines;
  const texts = plain.split("\n");
  const synced = supplied.length ? plain : previous.length && texts.length === previous.length
    ? serializeLrc(previous.map((line, i) => ({ time: line.time, text: texts[i] }))) : "";
  const result = { ...entry, v: 1, source: "manual", plain: supplied.length ? supplied.map((line) => line.text).join("\n") : plain, synced, savedAt: Date.now() };
  if (!synced) delete result.generatedTimingApplied;
  delete result.aligned;
  delete result.userSynced;
  delete result.offsetSec;
  result.instrumental = false;
  return result;
}

// Temporary markers for the manual timing editor, never saved or presented
// as synchronized lyrics until the user taps or the vocal alignment succeeds.
export function untimedLines(text, duration) {
  const texts = String(text || "").replace(/\r\n?/g, "\n").split("\n");
  return texts.map((text, i) => ({ text, time: i * Math.max(1, duration || texts.length * 3) / texts.length }));
}
