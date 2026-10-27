import { mixerState, trackIndex } from "./state.js";
import { isPercussion } from "./constants.js";
import { transposeKey } from "./keyLabel.js";
import { t, onLanguageChange } from "./i18n.js";

let track = null, segments = [], time = 0, pending = null, token = 0, lastLabel = "";
function labelFor(value, shift) {
  const m = /^([A-G][#b]?):(maj|min|7)$/.exec(value || "");
  if (!m) return "—";
  const key = transposeKey(m[1] + " maj", shift);
  return key ? key.split(" ")[0] + (m[2] === "min" ? "m" : m[2] === "7" ? "7" : "") : "—";
}
export function refreshAnalysisChord() {
  const el = document.getElementById("summary-chord");
  if (!el) return;
  const shifts = new Set(Object.keys(trackIndex || {}).filter(n => n !== "original" && !isPercussion(n) && mixerState[n]).map(n => Number(mixerState[n].pitch) || 0));
  let chord = null;
  for (const item of segments) {
    if (time >= item.start_time && time < item.end_time) { chord = item.chord; break; }
  }
  const label = shifts.size > 1 ? "—" : labelFor(chord, shifts.size === 1 ? [...shifts][0] : 0);
  if (lastLabel !== label) { el.textContent = label; lastLabel = label; }
  el.title = t("chords.hint");
}
export function updateAnalysisChordTime(value) {
  if (Number.isFinite(value)) time = value;
  refreshAnalysisChord();
}
async function load(id) {
  const stamp = ++token;
  segments = []; time = 0; lastLabel = ""; refreshAnalysisChord();
  const btn = document.getElementById("chords-analyze"), status = document.getElementById("chords-status");
  if (btn) { btn.hidden = !id; btn.disabled = !!pending; }
  if (status) status.textContent = pending === id ? t("chords.running") : "";
  if (!id) return;
  try {
    const response = await fetch("/api/jobs/" + encodeURIComponent(id) + "/chords", {cache:"no-store"});
    if (stamp !== token || track !== id) return;
    if (response.status === 404) return;
    if (!response.ok) throw new Error("load failed");
    const result = await response.json();
    if (stamp !== token || track !== id) return;
    segments = Array.isArray(result.segments) ? result.segments : [];
    if (btn) btn.hidden = true;
    if (status) status.textContent = t("chords.preview");
    refreshAnalysisChord();
  } catch {
    if (stamp === token && status) status.textContent = t("chords.failed");
  }
}
async function analyze() {
  const id = track;
  if (!id || pending) return;
  pending = id;
  const btn = document.getElementById("chords-analyze"), status = document.getElementById("chords-status");
  if (btn) btn.disabled = true;
  if (status) status.textContent = t("chords.running");
  try {
    const response = await fetch("/api/jobs/" + encodeURIComponent(id) + "/chords", {method:"POST"});
    if (!response.ok) throw new Error("analysis failed");
    if (track === id) await load(id);
  } catch {
    if (track === id && status) status.textContent = t("chords.failed");
  } finally {
    pending = null;
    if (btn && track) btn.disabled = false;
  }
}
document.addEventListener("trackwillopen", e => { track = e.detail?.jobId || null; void load(track); });
document.addEventListener("DOMContentLoaded", () => document.getElementById("chords-analyze")?.addEventListener("click", () => void analyze()));
onLanguageChange(refreshAnalysisChord);
