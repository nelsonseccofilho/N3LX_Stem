import { getBars } from "./beatgrid.js";
import { t, onLanguageChange } from "./i18n.js";

// The beat grid has beats per bar, not a note-value denominator. Never turn
// a detected count into an asserted 4/4 or 6/8 time signature.
export function refreshAnalysisMeter() {
  const node = document.getElementById("summary-meter");
  if (!node) return;
  const bars = getBars();
  const values = [...new Set(bars.map(b => b.beats_per_bar).filter(n => Number.isInteger(n) && n > 0))];
  node.textContent = values.length > 1 ? t("meta.meterVaries") : values.length === 1 ? t("meta.meterBeats", { count: values[0] }) : "—";
  node.title = values.length ? t("meta.meterHint") : t("meta.meterUnavailable");
}
document.addEventListener("trackwillopen", () => {
  const node = document.getElementById("summary-meter");
  if (node) { node.textContent = "—"; node.title = ""; }
});
document.addEventListener("playbackready", refreshAnalysisMeter);
onLanguageChange(refreshAnalysisMeter);
