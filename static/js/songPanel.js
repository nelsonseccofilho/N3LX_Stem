import { getSongOrganization, organizeSong } from "./catalog.js";
import { getSetlistChoices, addSongToSetlist } from "./setlist.js";
import { t, onLanguageChange } from "./i18n.js";
import { openGuitarDetail } from "./guitarDetail.js";

const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
function button(label, action, cls = "") {
  const node = el("button", cls, label); node.type = "button";
  node.addEventListener("click", action); return node;
}

// Global song controls keep their original nodes/IDs and audio event bindings.
// Only their layout changes; the mixer and playlist scopes remain independent.
export function initSongPanel() {
  const card = document.getElementById("nowPlayingPanel");
  if (!card || card.dataset.songPanelReady) return;
  card.dataset.songPanelReady = "1";
  // Loop text fields now sit near the import form. Enter must never submit it.
  card.addEventListener("keydown", event => {
    if (event.key === "Enter" && event.target.matches("input")) event.preventDefault();
  });
  const strip = card.querySelector(".footer-clusters");
  strip.append(card.querySelector(".footer-track-actions"));
  const position = card.querySelector(".footer-group-position .footer-group-body");
  const scrub = document.getElementById("footer-scrub");
  position.insertBefore(scrub, document.getElementById("t-loop"));
  scrub.setAttribute("aria-valuemin", "0"); scrub.setAttribute("aria-valuemax", "100");
  scrub.setAttribute("aria-valuenow", "0"); scrub.setAttribute("aria-disabled", "true");
  const note = document.getElementById("t-metro-note");
  document.getElementById("t-metro-panel").append(note);
  const bounds = card.querySelector(".footer-loop-times-wrap");
  bounds.classList.add("song-loop-panel", "hidden"); bounds.id = "song-loop-panel";
  const loopMore = button("⌄", () => {}, "song-small-btn"); loopMore.id = "song-loop-more";
  loopMore.setAttribute("aria-controls", bounds.id); position.append(loopMore);
  const menuWrap = el("div", "song-menu-wrap");
  const menuButton = button("⋯", () => {}, "song-small-btn song-menu-button");
  menuButton.id = "song-menu-button"; menuButton.setAttribute("aria-controls", "song-menu");
  menuButton.setAttribute("data-i18n-title", "song.actions"); menuButton.setAttribute("data-i18n-aria-label", "song.actions");
  loopMore.setAttribute("data-i18n-title", "song.loopOptions"); loopMore.setAttribute("data-i18n-aria-label", "song.loopOptions");
  const metroLabel = card.querySelector(".footer-group-click .footer-group-label");
  metroLabel.dataset.i18n = "song.metronome"; metroLabel.textContent = t("song.metronome");
  const menu = el("div", "song-menu hidden"); menu.id = "song-menu";
  menu.setAttribute("role", "group");
  menuWrap.append(menuButton, menu); card.querySelector(".track-panel-head").append(menuWrap);
  const notice = el("div", "song-notice"); notice.setAttribute("role", "status"); card.append(notice);
  let closeMenu;
  const renderMenu = () => {
    menu.replaceChildren();
    const song = getSongOrganization();
    for (const [key, mode] of [["song.addSetlist", "setlist"], ["song.moveCollection", "collection"], ["song.newCollection", "new-collection"]]) {
      const item = button(t(key), () => { closeMenu(); organizeDialog(song, mode, notice, menuButton); });
      item.disabled = !song.ready; menu.append(item);
    }
    menu.append(button(t("song.editInfo"), () => { closeMenu(); document.getElementById("np-details-btn").click(); }));
    const guitars = button(t("guitar.title"), () => { closeMenu(); openGuitarDetail(song, menuButton); });
    guitars.disabled = !song.ready; menu.append(guitars);
  };
  closeMenu = wirePanel(menuButton, menu, renderMenu);
  wirePanel(loopMore, bounds);
  const translate = () => {
    menuButton.title = t("song.actions"); menuButton.setAttribute("aria-label", t("song.actions"));
    loopMore.title = t("song.loopOptions"); loopMore.setAttribute("aria-label", t("song.loopOptions"));
    renderMenu();
  };
  translate(); onLanguageChange(translate);
  document.addEventListener("trackwillopen", () => { notice.textContent = ""; closeMenu(); });
}

function wirePanel(trigger, panel, onOpen) {
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("aria-haspopup", "true");
  const close = () => { panel.classList.add("hidden"); trigger.setAttribute("aria-expanded", "false"); };
  trigger.addEventListener("click", event => {
    event.stopPropagation(); const wasOpen = !panel.classList.contains("hidden");
    document.dispatchEvent(new Event("songpanelclose"));
    if (wasOpen) return;
    onOpen?.(); panel.classList.remove("hidden"); trigger.setAttribute("aria-expanded", "true");
    panel.querySelector("button:not(:disabled), input:not(:disabled)")?.focus();
  });
  panel.addEventListener("click", event => event.stopPropagation());
  document.addEventListener("songpanelclose", close);
  document.addEventListener("click", close);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !panel.classList.contains("hidden")) { close(); trigger.focus(); }
  });
  window.addEventListener("resize", close);
  document.addEventListener("trackwillopen", close);
  return close;
}

function organizeDialog(song, mode, notice, trigger) {
  const playlist = mode === "setlist", create = mode === "new-collection";
  const title = t(playlist ? "song.addSetlist" : create ? "song.newCollection" : "song.moveCollection");
  const dialog = el("dialog", "song-organize-dialog");
  const form = el("form", "song-organize-form");
  const heading = el("h2", "", title); heading.id = "song-organize-title";
  dialog.setAttribute("aria-labelledby", heading.id);
  form.append(heading, el("p", "song-organize-title", song.title));
  const select = el("select"); select.setAttribute("aria-label", title);
  const choices = playlist ? getSetlistChoices() : song.collections;
  for (const choice of choices) {
    const option = el("option", "", choice.name); option.value = choice.id; option.disabled = Boolean(choice.disabled);
    option.selected = Boolean(choice.selected); select.append(option);
  }
  if (playlist) { const option = el("option", "", t("setlist.new")); option.value = "__new"; select.append(option); }
  const nameLabel = el("label", "song-name-field", t(playlist ? "setlist.name" : "folderEditor.nameLabel"));
  const input = el("input"); input.type = "text"; input.maxLength = playlist ? 80 : 100; input.value = create ? song.title : "";
  nameLabel.append(input);
  const update = () => { nameLabel.hidden = !(create || select.value === "__new"); input.required = !nameLabel.hidden; };
  select.addEventListener("change", update);
  if (!create) form.append(select);
  form.append(nameLabel); update();
  const error = el("p", "song-dialog-error"); error.setAttribute("role", "alert"); form.append(error);
  const actions = el("div", "song-dialog-actions");
  actions.append(button(t("folderEditor.cancel"), () => dialog.close()));
  const submit = el("button", "song-primary", t("folderEditor.save")); submit.type = "submit"; actions.append(submit); form.append(actions);
  form.addEventListener("submit", async event => {
    event.preventDefault(); submit.disabled = true; error.textContent = "";
    try {
      if (playlist) {
        const result = await addSongToSetlist(song.id, select.value, select.value === "__new" ? input.value : null);
        notice.textContent = t(result.exists ? "song.alreadyAdded" : "song.added", { name: result.name });
      } else {
        const name = await organizeSong(song.id, select.value, create ? input.value : null);
        notice.textContent = t("song.moved", { name });
      }
      dialog.close();
    } catch (problem) { error.textContent = problem.message; submit.disabled = false; }
  });
  dialog.addEventListener("close", () => { dialog.remove(); trigger.focus(); }, { once: true });
  dialog.append(form); document.body.append(dialog); dialog.showModal();
  (create ? input : select).focus();
}
