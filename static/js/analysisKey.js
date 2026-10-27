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
  const node = document.getElementById("summary-key");
  if (!node) return;
  const names = Object.keys(trackIndex || {}).filter(name => name !== "original" && !isPercussion(name) && mixerState[name]);
  const shifts = new Set(names.map(name => Number(mixerState[name].pitch) || 0));
  const mixed = shifts.size > 1;
  const shift = shifts.size === 1 ? [...shifts][0] : 0;
  const original = formatKey(originalKey, originalScale, t);
  const adjusted = transposeKey(originalKey, shift);
  node.textContent = mixed && originalKey ? t("key.mixed") : formatKey(adjusted, originalScale, t) || "—";
  const symbol = document.getElementById("summary-key-symbol");
  if (symbol) {
    symbol.textContent = mixed ? "—" : keySymbol(adjusted, originalScale) || "—";
    symbol.title = t("meta.keySymbol");
  }
  node.title = original ? t("key.originalHint", { key: original }) : "";
  const confidence = document.getElementById("summary-confidence");
  if (confidence) confidence.title = original ? t("key.originalConfidence") : "";
}
onLanguageChange(refreshAnalysisKey);
