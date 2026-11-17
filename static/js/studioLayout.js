import { t, onLanguageChange } from "./i18n.js";
import { initHeaderCompactV2 } from "./headerCompactV2.js";
import { initHeaderCompactV3 } from "./headerCompactV3.js";
import { initHeaderReextract } from "./headerReextract.js";

// Compact studio chrome. Move the EXISTING controls, never clone them:
// audio, search, drag/drop and submit listeners must retain their DOM nodes.
export function initStudioLayout() {
  const app = document.querySelector(".app");
  const form = document.getElementById("job-form");
  if (!app || !form || form.dataset.layoutReady) return;
  form.dataset.layoutReady = "compact-header-v1";

  const toggle = document.getElementById("importLayoutToggle");
  const workspace = document.getElementById("headerImportWorkspace");
  if (!toggle || !workspace) return;
  let expanded = toggle.checked;
  const refresh = () => {
    toggle.checked = expanded;
    form.classList.toggle("header-import-open", expanded);
    const label = document.getElementById("importLayoutLabel");
    label.textContent = t(expanded ? "layout.collapseImport" : "layout.newExtraction");
    toggle.setAttribute("aria-label", label.textContent);
    toggle.title = label.textContent;
  };
  const close = (restoreFocus = false) => {
    if (!expanded) return;
    expanded = false;
    refresh();
    if (restoreFocus) toggle.focus();
  };
  toggle.addEventListener("change", () => {
    expanded = toggle.checked;
    refresh();
    if (!expanded) return;
    requestAnimationFrame(() => {
      window.dispatchEvent(new Event("resize"));
      document.getElementById("url")?.focus();
    });
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && expanded && workspace.contains(document.activeElement)) {
      event.preventDefault(); close(true);
    }
  });
  document.addEventListener("pointerdown", event => {
    if (expanded && !form.contains(event.target)) close(false);
  });
  document.addEventListener("trackwillopen", () => close(false));
  onLanguageChange(refresh);
  refresh();
  initHeaderCompactV2();
  initHeaderCompactV3();
  initHeaderReextract();
}
