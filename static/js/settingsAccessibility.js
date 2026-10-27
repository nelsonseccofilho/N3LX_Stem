import { t } from "./i18n.js";

export function enhanceSettings(overlay, opener) {
  const tabs = [...overlay.querySelectorAll(".settings-tab")];
  const panes = [...overlay.querySelectorAll(".settings-pane")];
  const tablist = overlay.querySelector(".settings-tabs");
  tablist.setAttribute("aria-label", t("settings.tabs"));
  function sync() {
    for (const tab of tabs) {
      const selected = tab.classList.contains("active");
      tab.id = `settings-tab-${tab.dataset.tab}`;
      tab.setAttribute("aria-controls", `settings-pane-${tab.dataset.tab}`);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    }
    for (const pane of panes) {
      pane.id = `settings-pane-${pane.dataset.pane}`;
      pane.setAttribute("role", "tabpanel");
      pane.setAttribute("aria-labelledby", `settings-tab-${pane.dataset.pane}`);
      pane.hidden = pane.classList.contains("hidden");
      pane.tabIndex = 0;
    }
  }
  for (const tab of tabs) tab.addEventListener("click", sync);
  tablist.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const current = tabs.indexOf(document.activeElement);
    const index = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
      (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[index].click(); tabs[index].focus();
    tabs[index].scrollIntoView({ block: "nearest", inline: "nearest" });
  });
  overlay.addEventListener("keydown", event => {
    if (event.key !== "Tab") return;
    const items = [...overlay.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]')]
      .filter(el => el.getClientRects().length && !el.closest("[hidden], .hidden"));
    if (!items.length) return;
    const first = items[0], last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  sync();
  tabs[0].focus();
  overlay._restoreFocus = () => { if (opener?.isConnected) opener.focus(); };
}
