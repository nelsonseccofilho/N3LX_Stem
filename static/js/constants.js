import { t, TRANSLATIONS } from "./i18n.js";

// Fallback list used before /api/config responds. Kept in sync with
// STEM_NAMES in app/core/config.py — the API is the canonical source.
export let STEM_NAMES = ["vocals", "drums", "bass", "guitar", "piano", "other"];
export let TRACK_NAMES = ["original", ...STEM_NAMES];

// Stems from the on-demand lead/backing vocal split (#275, EXTRA_STEM_NAMES
// in app/core/config.py). Not folded into STEM_NAMES/TRACK_NAMES -- most jobs
// never run this split -- but the player/mixer render them as real lanes,
// swapped in for "vocals", via effectiveStemOrder() below.
export let EXTRA_STEM_NAMES = ["lead_vocals", "backing_vocals"];

let laneLabels = {};
let importedLabels = {};
let importedActiveNames = [];
export let defaultSeparationProfile = "standard";
export function setDefaultSeparationProfile(profile) {
  defaultSeparationProfile = profile === "complete" ? "complete" : "standard";
  if (typeof document !== "undefined") document.dispatchEvent(new CustomEvent("separationprofilechange"));
}
let importedPercussion = [];
export const DRUM_STEMS = ["drum_kick", "drum_snare", "drum_toms", "drum_hh", "drum_ride", "drum_crash"];
export function applyStudioLayout(layout) { importedLabels = layout?.labels || {}; importedActiveNames = layout?.profile === "complete" ? (layout.active_names || []) : []; importedPercussion = layout?.percussion_names || []; }
// A separation residual can include tonal material; percussion-only lanes stay fixed.
// This shared predicate governs mixer buttons, global pitch and the audio worklet.
export function isPercussion(name) {
  if (name === "residual_mix") return false;
  return name === "drums" || name === "residual_drums" || name === "drum_recovery" || name === "residual_drums_refined" || DRUM_STEMS.includes(name) || importedPercussion.includes(name);
}
export async function syncStemNamesFromAPI() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return;
    const data = await res.json();
    laneLabels = data.stem_labels || {};
    setDefaultSeparationProfile(data.separation_profile);
    for (const name of data.extra_stem_names || []) {
      STEM_COLORS[name] ||= name.startsWith("drum_") ? "#e89048" : name.startsWith("residual_") ? "#88a8c8" : "#a2b9db";
    }
    if (Array.isArray(data.stem_names) && data.stem_names.length > 0) {
      STEM_NAMES = data.stem_names;
      TRACK_NAMES = ["original", ...STEM_NAMES];
    }
    if (Array.isArray(data.extra_stem_names) && data.extra_stem_names.length > 0) {
      EXTRA_STEM_NAMES = data.extra_stem_names;
    }
  } catch (e) {
    console.warn("[constants] failed to sync stem names from API:", e);
  }
}

// One shared order for ready-lane navigation, mixer, waveforms and playback.
// Keep reconstruction residues beside the corresponding source family.
export const STEM_GROUPS = [
  { id: "voices", names: ["vocals", "lead_vocals", "backing_vocals"] },
  { id: "vocalResidual", names: ["residual_vocals"] },
  { id: "strings", names: ["bass", "guitar"] },
  { id: "keys", names: ["piano"] },
  { id: "other", names: ["other"] },
  { id: "separationResidual", names: ["residual_mix"] },
  { id: "drums", names: ["drums", ...DRUM_STEMS] },
  { id: "drumResidual", names: ["residual_drums"] },
];

export function stemLaneGroups(names) {
  const remaining = new Set(names);
  const groups = STEM_GROUPS.flatMap((group) => {
    const members = group.names.filter((name) => remaining.delete(name));
    return members.length ? [{ ...group, names: members }] : [];
  });
  // Custom DAW imports retain their own track sequence and names.
  return [...groups, ...remaining].map((group) => typeof group === "string"
    ? { id: group, names: [group], custom: true } : group);
}

function orderStemNames(names) {
  if (names.some((name) => name.startsWith("studio_") || name === "reaper_master")) return names;
  return stemLaneGroups(names).flatMap((group) => group.names);
}

export function effectiveStemOrder(presentNames) {
  // Older complete jobs stored bass first; normalize on read without changing
  // audio, extraction metadata or the user's mix settings.
  if (importedActiveNames.length) return orderStemNames(importedActiveNames.filter((n) => presentNames.has(n)));
  const splitDone = presentNames.has("lead_vocals") && presentNames.has("backing_vocals");
  const imported = EXTRA_STEM_NAMES.filter((n) => n.startsWith("studio_") && presentNames.has(n));
  if (imported.length) return imported;
  if (presentNames.has("reaper_master")) return ["reaper_master"];
  const drumsDone = DRUM_STEMS.every((n) => presentNames.has(n));
  const order = STEM_NAMES.flatMap((n) => {
    if (n === "vocals" && splitDone) return ["lead_vocals", "backing_vocals"];
    if (n === "drums" && drumsDone) return DRUM_STEMS;
    return [n];
  });
  return orderStemNames([...order, ...EXTRA_STEM_NAMES.filter((n) => n.startsWith("residual_") && presentNames.has(n))]);
}

// A Proxy, not a plain object, so every lookup resolves through the CURRENT
// language live -- a plain object would freeze these labels in whatever
// language was active the moment this module first loaded. Callers keep their
// existing `STEM_DISPLAY[name] || name` fallback pattern unchanged: an
// unrecognized name (not one of ours) still yields undefined, same as a plain
// object would, rather than the i18n engine's own missing-key fallback
// (which returns the raw dictionary key string -- wrong here).
export const STEM_DISPLAY = new Proxy({}, {
  get(_target, prop) {
    if (typeof prop !== "string") return undefined;
    if (importedLabels[prop]) return importedLabels[prop];
    if (laneLabels[prop]) return laneLabels[prop];
    const key = `stem.${prop}`;
    return key in TRANSLATIONS.en ? t(key) : undefined;
  },
});

// FL Studio-style channel palette: saturated but slightly dusty, designed
// to read well on a dark background.
export const STEM_COLORS = {
  vocals: "#e85f6f",
  drums: "#e89048",
  bass: "#e8b848",
  guitar: "#88d878",
  piano: "#b88fe8",
  other: "#88a8c8",
  original: "#a8b0bd",
  lead_vocals: "#e8748a",
  backing_vocals: "#c98fe0",
};

export const PROGRESS_COLOR = "#3a3a3a";

export const LOOP_DEFAULT_START_FRAC = 0.25;
export const LOOP_DEFAULT_END_FRAC = 0.5;

export const LANE_VOLUME_MAX = 2;