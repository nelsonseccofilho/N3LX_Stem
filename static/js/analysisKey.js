import { refreshAnalysisChord } from "./analysisChords.js";
import { mixerState, trackIndex } from "./state.js";
import { isPercussion } from "./constants.js";
import { formatKey, transposeKey, keySymbol } from "./keyLabel.js";
import { t, onLanguageChange } from "./i18n.js";

let originalKey = "", originalScale = "";
export function setAnalyzedKey(key, scale) {
  originalKey = key || "";
  originalScale = scale || "";
  refreshAnalysisKey();
}
export function refreshAnalysisKey() {
  refreshAnalysisChord();
  const node = document.getElementById("summary-key");
  if (!node) return;
  const names = Object.keys(trackIndex || {}).filter(name => name !== "original" && !isPercussion(name) && mixerState[name]);
  const shifts = new Set(names.map(name => Number(mixerState[name].pitch) || 0));
  const mixed = shifts.size > 1;
  const shift = shifts.size === 1 ? [...shifts][0] : 0;
  const original = formatKey(originalKey, originalScale, t);
  const adjusted = transposeKey(originalKey, shift);
  const readable = formatKey(adjusted, originalScale, t);
  const shorthand = keySymbol(adjusted, originalScale);
  const cinema = document.getElementById('cinemaKey');
  if (cinema) cinema.textContent = !original ? 'Tom não identificado' :
    `${original} → ${mixed ? t('key.mixed') : readable || 'Tom não identificado'}`;
  // Show the familiar musician shorthand as the primary value, and spell out
  // the mode below so F# major cannot be mistaken for F# minor.
  node.textContent = mixed && originalKey ? t("key.mixed") : shorthand || readable || "—";
  const symbol = document.getElementById("summary-key-symbol");
  if (symbol) {
    // The user prefers one concise key notation. Preserve the expanded mode
    // as a tooltip rather than repeating it in the card.
    symbol.textContent = "";
    symbol.title = readable || t("meta.keySymbol");
    symbol.setAttribute("aria-label", readable || t("meta.keySymbol"));
  }
  node.title = original ? t("key.originalHint", { key: original }) : "";
  const confidence = document.getElementById("summary-confidence");
  if (confidence) confidence.title = original ? t("key.originalConfidence") : "";
}
onLanguageChange(refreshAnalysisKey);
