// A track's key as one label, "B minor" or "B harmonic minor" (#736).
//
// Analysis stores the key as "B min" and the scale separately as "Natural
// Minor", and the analysis strip used to show both plus a Scale card of its
// own: "D maj", then "Major", then "Major" again. One label says it once.
//
// Note names stay as letters in every language, the convention DAWs and chord
// charts use, rather than H or Si. The mode is translated and placed by a
// template, because word order differs ("B minor", "B-Moll" style, "B 小调").

// The scale names analysis can produce, to the mode each is shown as.
const MODE_KEYS = {
  "Major": "key.mode.major",
  "Natural Minor": "key.mode.minor",
  "Harmonic Minor": "key.mode.harmonicMinor",
};

/**
 * @param {string|null|undefined} key    as stored, e.g. "F# min"
 * @param {string|null|undefined} scale  as stored, e.g. "Harmonic Minor"
 * @param {(key: string, vars?: object) => string} t  the i18n lookup
 * @returns {string} the label, or "" when there is no key to show
 */
export function formatKey(key, scale, t) {
  const text = String(key ?? "").trim();
  if (!text) return "";
  const [tonic, suffix] = text.split(/\s+/);
  // A scale this does not know (or none, from tracks analysed before it was
  // stored) falls back on the key's own maj/min suffix.
  let modeKey = MODE_KEYS[scale];
  if (!modeKey && suffix === "maj") modeKey = "key.mode.major";
  if (!modeKey && suffix === "min") modeKey = "key.mode.minor";
  if (!modeKey) return text;
  return t("key.label", { tonic, mode: t(modeKey) });
}

// Transpose only known chromatic tonics; leave analysis data unchanged.
export function transposeKey(key, semitones) {
  const text = String(key ?? "").trim();
  if (!text) return "";
  const match = /^([A-G])([#b♯♭]?)(.*)$/.exec(text);
  if (!match || !Number.isInteger(semitones)) return semitones === 0 ? text : "";
  const natural = { C:0, D:2, E:4, F:5, G:7, A:9, B:11 };
  const accidental = match[2] === "#" || match[2] === "♯" ? 1 : match[2] === "b" || match[2] === "♭" ? -1 : 0;
  const names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
  if (semitones === 0) return text;
  return names[((natural[match[1]] + accidental + semitones) % 12 + 12) % 12] + match[3];
}
