// Precise correction of one lyric start after automatic alignment.
// Keep corrected text and the remaining matched anchors; manual correction wins.
import { applyTime } from "./lyricsSync.js";

export function parseLyricClock(value, duration = Infinity) {
  const raw = String(value ?? "").trim();
  const colon = /^(\d{1,3}):(\d{2})(?:\.(\d{1,2}))?$/.exec(raw);
  let seconds;
  if (colon) {
    const part = Number(colon[2]);
    if (part >= 60) return null;
    seconds = Number(colon[1]) * 60 + part +
      Number((colon[3] || "").padEnd(2, "0")) / 100;
  } else if (/^\d+(?:\.\d{1,2})?$/.test(raw)) {
    seconds = Number(raw);
  } else return null;
  return Number.isFinite(seconds) && seconds >= 0 && seconds <= duration ? seconds : null;
}

export function anchorFirstSungLine(lines, seconds, duration = Infinity) {
  if (!Array.isArray(lines) || !Number.isFinite(seconds) || seconds < 0 ||
      seconds > duration) return null;
  const index = lines.findIndex((line) => typeof line?.text === "string" &&
    line.text.trim() && line.text.trim() !== "♪");
  if (index < 0) return null;
  const adjusted = applyTime(lines, index, seconds, { mode: "push", max: duration });
  // Pause markers are display clears, not words. A clear immediately after
  // the new onset would hide the phrase while it is still being sung.
  const nextSung = adjusted.findIndex((line, i) =>
    i > index && typeof line?.text === "string" && line.text.trim() && line.text.trim() !== "♪");
  if (nextSung > index + 1 && adjusted[nextSung].time > seconds + 1.7) {
    const lastWord = adjusted[index].words?.filter((word) => Number.isFinite(word.time))
      .at(-1)?.time;
    const clearAt = Math.min(adjusted[nextSung].time - 0.2,
      Math.max(seconds + 1.5, Number.isFinite(lastWord) ? lastWord + 0.25 : seconds + 2));
    for (let i = index + 1; i < nextSung; i++) {
      if (!adjusted[i].text?.trim() && adjusted[i].time < clearAt)
        adjusted[i] = { ...adjusted[i], time: clearAt };
    }
  }
  return { lines: adjusted, index };
}
