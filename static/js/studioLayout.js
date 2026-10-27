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

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.id = "importLayoutToggle";
  toggle.className = "import-layout-toggle";
  toggle.setAttribute("aria-controls", "headerImportWorkspace");
  toggle.setAttribute("aria-expanded", "false");
  form.prepend(toggle);

  const workspace = document.createElement("section");
  workspace.id = "headerImportWorkspace";
  workspace.className = "header-import-workspace";
  workspace.setAttribute("role", "region");
  workspace.setAttribute("aria-label", "Importação e extração de stems");
  workspace.setAttribute("aria-labelledby", "importLayoutToggle");
  workspace.hidden = true;

  // Keep every original import setting in the original form. The loaded song,
  // favorites and transport remain visible when the workspace is open.
  for (const selector of [".daw-url-zone", ".daw-stem-section", ".structure-toggle", "#submit"]) {
    const control = form.querySelector(selector);
    if (control) workspace.append(control);
  }
  form.insertBefore(workspace, document.getElementById("nowPlayingPanel"));

  // The panel display toggles belong to the studio viewing toolbar, not
  // among the import settings. Preserve the original buttons and handlers.
  const panelToggles = form.querySelector(".daw-panel-toggles");
  const view = document.querySelector(".studio-view-tools");
  if (view && panelToggles) view.insertBefore(panelToggles, view.querySelector(".view-shortcuts"));

  form.classList.add("header-compact");
  let expanded = app.classList.contains("no-track");
  const refresh = () => {
    workspace.hidden = !expanded;
    form.classList.toggle("header-import-open", expanded);
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.textContent = t(expanded ? "layout.collapseImport" : "layout.newExtraction");
    toggle.title = toggle.textContent;
  };
  const close = (restoreFocus = false) => {
    if (!expanded) return;
    expanded = false;
    refresh();
    if (restoreFocus) toggle.focus();
  };
  toggle.addEventListener("click", () => {
    if (expanded) return close(true);
    expanded = true;
    refresh();
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
