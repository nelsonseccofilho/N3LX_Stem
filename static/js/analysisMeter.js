import { getBars, getBeats } from "./beatgrid.js";
import { t, onLanguageChange } from "./i18n.js";

// The beat grid has beats per bar, not a note-value denominator. Never turn
// a detected count into an asserted 4/4 or 6/8 time signature.
let lastTime = 0;
let rendered = "";
let lastSample = -1;
export function refreshAnalysisMeter(time = lastTime, force = true) {
  const node = document.getElementById("summary-meter");
  if (!node) return;
  if (Number.isFinite(time)) lastTime = Math.max(0, time);
  if (!force && lastSample >= 0 && Math.abs(lastTime - lastSample) < 0.1) return;
  lastSample = lastTime;
  const beats = getBeats(), bars = getBars();
  let lo = 0, hi = beats.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (beats[mid] <= lastTime) lo = mid + 1; else hi = mid;
  }
  const beatIndex = lo - 1;
  let mark = null;
  for (const bar of bars) {
    if (bar.beat <= beatIndex) mark = bar;
    else break;
  }
  const count = mark?.beats_per_bar;
  const label = Number.isInteger(count) && count > 0 ? t("meta.meterBeats", { count }) : "—";
  const hint = label === "—" ? t("meta.meterUnavailable") : t("meta.meterHint");
  if (force || rendered !== label || node.title !== hint) {
    node.textContent = label;
    node.title = hint;
    rendered = label;
  }
}
export function updateAnalysisMeterTime(time) { refreshAnalysisMeter(time, false); }
document.addEventListener("trackwillopen", () => {
  lastTime = 0; lastSample = -1; rendered = "";
  const node = document.getElementById("summary-meter");
  if (node) { node.textContent = "—"; node.title = ""; }
});
document.addEventListener("playbackready", () => refreshAnalysisMeter());
onLanguageChange(() => refreshAnalysisMeter());
