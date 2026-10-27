// Sidecar lyrics are a preview, never a replacement for a user's saved lyrics.
// This module has no DOM or backend dependencies, so the contract is testable.
const MAX_WORDS = 30000;
const MAX_SECONDS = 21600;
const MAX_TEXT = 120;

const stamp = (seconds) => {
  const cs = Math.max(0, Math.round(seconds * 100));
  return `${String(Math.floor(cs / 6000)).padStart(2, "0")}:${String(Math.floor(cs % 6000 / 100)).padStart(2, "0")}.${String(cs % 100).padStart(2, "0")}`;
};

export function karaokePreviewFromTiming(value, { title = "", artist = "", duration = 0 } = {}) {
  if (!value || value.v !== 1 || !Array.isArray(value.words) ||
      value.words.length < 3 || value.words.length > MAX_WORDS) return null;
  const words = [];
  let previous = -1;
  for (const item of value.words) {
    const text = item?.text;
    const start = item?.start;
    const end = item?.end;
    if (typeof text !== "string" || !text.trim() || text.length > MAX_TEXT ||
        /[<>\[\]]/.test(text) || typeof start !== "number" ||
        typeof end !== "number" || !Number.isFinite(start) || !Number.isFinite(end) ||
        start < 0 || end < start || end > MAX_SECONDS || start < previous - 0.02) return null;
    words.push({ text: text.trim(), start, end });
    previous = Math.max(previous, start);
  }
  const groups = [];
  let group = [];
  for (const word of words) {
    if (group.length && (word.start - group[group.length - 1].end >= 0.75 || group.length >= 9)) {
      groups.push(group);
      group = [];
    }
    group.push(word);
  }
  if (group.length) groups.push(group);
  // Generate LRC locally from validated word timestamps, never trust preview markup.
  const synced = groups.map((line) =>
    `[${stamp(line[0].start)}]` + line.map((word, index) =>
      `<${stamp(word.start)}>${word.text}${index < line.length - 1 ? " " : ""}`
    ).join("") + `<${stamp(line[line.length - 1].end)}>`
  ).join("\n");
  const plain = groups.map((line) => line.map((word) => word.text).join(" ")).join("\n");
  return {
    v: 1, source: "whisper", track: title, artist,
    duration, synced, plain, instrumental: false,
    machinePreview: true, timingStatus: "machine_unverified",
  };
}

export function hasProtectedLyrics(entry, editing = false) {
  return Boolean(editing || entry?.source === "manual" ||
    (typeof entry?.userSynced === "string" && entry.userSynced.trim()));
}

/**
 * Reuse generated word times only for an exact, in-order match. This preserves
 * edited punctuation and line breaks, never invents a timestamp for a changed
 * word, and leaves the stored entry untouched.
 */
export function timingForMatchingEditedLyrics(entry, timing) {
  if (typeof entry?.plain !== "string" || !entry.plain.trim() ||
      !karaokePreviewFromTiming(timing)) return null;
  const lines = entry.plain.normalize("NFC").split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const words = lines.flatMap(line => line.split(/\s+/));
  const normal = value => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
  if (!words.length || words.length > timing.words.length ||
      words.some((word, i) => /[<>\[\]]/.test(word) || !normal(word) ||
        normal(word) !== normal(timing.words[i].text))) return null;
  let index = 0;
  const synced = lines.map(line => {
    const parts = line.split(/\s+/);
    const first = timing.words[index];
    const fragments = parts.map((word, i) => {
      const item = timing.words[index++];
      return `<${stamp(item.start)}>${word}${i + 1 < parts.length ? " " : ""}`;
    });
    const last = timing.words[index - 1];
    return `[${stamp(first.start)}]${fragments.join("")}<${stamp(last.end)}>`;
  }).join("\n");
  return { ...entry, synced, generatedTimingApplied: true };
}
