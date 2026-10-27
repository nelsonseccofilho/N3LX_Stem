// Header v3 is additive over the user's already-installed compact header v2.
// No transport nodes are cloned or re-bound; existing timeupdate/seek stay authoritative.
import { onLanguageChange } from "./i18n.js";

export function initHeaderCompactV3() {
  const app = document.querySelector(".app.daw.header-v2");
  const card = document.querySelector("#job-form.header-compact #nowPlayingPanel");
  const play = card?.querySelector("#t-play");
  const seek = card?.querySelector("#footer-scrub");
  const fill = card?.querySelector("#footer-scrub-fill");
  const sidebar = document.getElementById("sidebarCollapseBtn");
  if (!app || !card || !play || !seek || !fill || !sidebar) return;
  if (app.classList.contains("header-v3")) return;

  // The single updateFooterTimes() clock in transport.js already writes
  // #footer-scrub-fill.style.width. CSS v3 makes that fill visible.
  const icon = sidebar.querySelector("svg");
  if (icon) {
    icon.setAttribute("viewBox", "0 0 24 24");
    icon.innerHTML = '<path d="m15 18-6-6 6-6" stroke-linecap="round" stroke-linejoin="round"/>';
  }
  const syncSidebarLabel = () => {
    const expanded = sidebar.getAttribute("aria-expanded") !== "false";
    const portuguese = document.documentElement.lang?.toLowerCase().startsWith("pt");
    const label = expanded
      ? (portuguese ? "Recolher barra lateral" : "Collapse sidebar")
      : (portuguese ? "Expandir barra lateral" : "Expand sidebar");
    sidebar.title = label;
    sidebar.setAttribute("aria-label", label);
  };
  // The pre-existing catalog code owns the state; observe rather than
  // reimplement clicks, storage, or the sidebar collapse operation.
  sidebar.removeAttribute("data-i18n-title");
  sidebar.removeAttribute("data-i18n-aria-label");
  new MutationObserver(syncSidebarLabel).observe(sidebar, {
    attributes: true, attributeFilter: ["aria-expanded"],
  });
  onLanguageChange(syncSidebarLabel);
  syncSidebarLabel();

  app.classList.add("header-v3");
}
