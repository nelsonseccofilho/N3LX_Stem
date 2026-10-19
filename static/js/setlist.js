import { createSetlistPlayer } from "./setlistPlayer.js";
import { normalizeSetlists, newPlaylist, copyMix, applyMixToPlaylist } from "./setlistLibrary.js";
import { storeGet, storeSet, flushStoreWrites, fmtTime } from "./utils.js";
import { stopTransport, startPreparedPlayback, getMetronomePrefs, setMetronomePreferenceScope } from "./transport.js";
import { t, onLanguageChange } from "./i18n.js";

const KEY = "stemdeck:setlist";
let controller, options, database, controlled = 0, editing = null, baseMetro = null;
let persistence = Promise.resolve(), saveTimer = null;
const model = () => controller?.state() || { ids: [], index: -1, status: "idle", busy: false };
const current = () => database?.playlists.find(p => p.id === database.selectedId);
const trackMap = () => new Map((options?.tracks() || []).map(track => [track.id, track]));
const makeId = () => crypto.randomUUID();
function ownTransport(fn) { controlled++; try { return fn(); } finally { controlled--; } }
function queueSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => { saveTimer = null; flushSetlist(); }, 250);
}
async function flushSetlist() {
  if (!database) return;
  clearTimeout(saveTimer); saveTimer = null;
  const snapshot = structuredClone(database);
  persistence = persistence.then(() => storeSet(KEY, snapshot)).catch(e => console.warn("[setlist] save failed", e));
  await persistence;
}
function enterScope(playlist, jobId) {
  if (!baseMetro) baseMetro = getMetronomePrefs();
  editing = { playlistId: playlist.id, jobId };
  setMetronomePreferenceScope({ prefs: { ...baseMetro, ...playlist.metro }, save(prefs) {
    playlist.metro = prefs; queueSave(); repaint();
  } });
}
function leaveScope() {
  editing = null;
  setMetronomePreferenceScope(null, baseMetro);
  baseMetro = null;
}
function mixContext(playlist, entry) {
  return { id: `${playlist.id}:${entry.id}`, mix: copyMix(entry.mix), save(mix) {
    entry.mix = copyMix(mix); queueSave();
  } };
}
function openReady(id, signal) {
  const playlist = current(), entry = playlist.entries.find(e => e.id === id);
  enterScope(playlist, id);
  return new Promise((resolve, reject) => {
    let settled = false;
    const done = error => {
      if (settled) return; settled = true;
      clearTimeout(timer);
      document.removeEventListener("playbackready", ready);
      document.removeEventListener("playbackfailed", failed);
      signal.removeEventListener("abort", aborted);
      error ? reject(error) : resolve();
    };
    const ready = event => { if (event.detail?.jobId === id) done(); };
    const failed = event => { if (event.detail?.jobId === id) done(new Error(t("setlist.loadError"))); };
    const aborted = () => done(new DOMException("Cancelled", "AbortError"));
    const timer = setTimeout(() => done(new Error(t("setlist.loadError"))), 120000);
    document.addEventListener("playbackready", ready);
    document.addEventListener("playbackfailed", failed);
    signal.addEventListener("abort", aborted, { once: true });
    if (signal.aborted) { aborted(); return; }
    if (!entry || !trackMap().has(id)) { done(new Error(t("setlist.unavailable"))); return; }
    flushSetlist().then(() => options.open(id, { source: "setlist", signal, mixContext: mixContext(playlist, entry) }))
      .then(ok => { if (!ok) done(new Error(t("setlist.unavailable"))); }).catch(done);
  });
}
function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function button(text, label, click, disabled = false) {
  const el = element("button", "setlist-button", text);
  el.type = "button"; el.setAttribute("aria-label", label); el.title = label;
  el.disabled = disabled; el.addEventListener("click", click); return el;
}
function statusText(s, tracks) {
  if (s.status === "error") return `${t("setlist.error")} · ${tracks.get(s.currentId)?.title || s.currentId}. ${s.error}`;
  const label = t(`setlist.${s.status}`);
  return s.index < 0 ? label : `${s.index + 1}/${s.ids.length} · ${label} · ${tracks.get(s.currentId)?.title || s.currentId}`;
}
function repaint() {
  options?.changed();
  const s = model(), tracks = trackMap(), bar = document.getElementById("setlistBar");
  if (!bar) return;
  bar.replaceChildren();
  bar.hidden = !editing && !s.busy && !["error", "completed"].includes(s.status);
  if (bar.hidden) return;
  const playlist = database.playlists.find(p => p.id === editing?.playlistId) || current();
  const text = s.busy || s.status === "error" || s.status === "completed" ? statusText(s, tracks) : t("setlist.editing");
  const status = element("span", "setlist-bar-status", `${playlist.name} · ${text}`);
  status.setAttribute("role", "status"); bar.append(status);
  if (s.busy) {
    bar.append(button("‹", t("setlist.previous"), () => controller.previous(), s.index <= 0 || s.status === "loading"));
    bar.append(button("›", t("setlist.next"), () => controller.next(), s.index + 1 >= s.ids.length || s.status === "loading"));
  }
  bar.append(button("Setlist", t("setlist.open"), options.show));
  bar.append(button(t("setlist.leave"), t("setlist.leave"), async () => {
    const id = editing?.jobId; controller.cancel(); leaveScope(); await flushSetlist();
    if (id) await options.open(id); repaint();
  }));
}
function replaceEntries(entries) {
  current().entries = entries;
  controller.setItems(entries.map(e => e.id)); queueSave();
}
async function changePlaylist(id) {
  if (model().busy) return;
  const wasEditing = editing?.jobId;
  leaveScope(); database.selectedId = id;
  controller.setItems(current().entries.map(e => e.id)); queueSave();
  if (wasEditing) await options.open(wasEditing);
}
async function adjust(playlist, entry) {
  if (model().busy) controller.cancel();
  enterScope(playlist, entry.id); repaint();
  await flushSetlist();
  await options.open(entry.id, { source: "setlist-edit", mixContext: mixContext(playlist, entry) });
}
export async function initSetlist(config) {
  options = config;
  database = normalizeSetlists(await storeGet(KEY, {}), makeId);
  controller = createSetlistPlayer({ open: openReady,
    play: () => ownTransport(() => startPreparedPlayback(current().metro)),
    stop: () => ownTransport(stopTransport), changed: repaint });
  controller.setItems(current().entries.map(e => e.id));
  document.addEventListener("trackplaybackended", event => controller.ended(event.detail?.jobId));
  document.addEventListener("playbackfailed", event => {
    if (model().busy && event.detail?.jobId === model().currentId) controller.fail(event.detail.message || t("setlist.loadError"));
  });
  document.addEventListener("trackwillopen", event => {
    if (!["setlist", "setlist-edit"].includes(event.detail?.source)) {
      if (model().busy) controller.cancel(false);
      leaveScope(); repaint();
    }
  });
  document.addEventListener("playbackloading", event => {
    if (model().busy && event.detail?.jobId !== model().currentId) { controller.cancel(false); leaveScope(); repaint(); }
  });
  document.addEventListener("transportintent", event => {
    if (controlled) return;
    if (model().status === "loading" && event.detail.action === "play") {
      event.preventDefault(); controller.cancel(); return;
    }
    if (editing && !model().busy && event.detail.action === "play") {
      const index = current().entries.findIndex(entry => entry.id === editing.jobId);
      if (index >= 0) { event.preventDefault(); controller.start(index); return; }
    }
    controller.transport(event.detail.action);
  });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") flushSetlist(); });
  onLanguageChange(repaint);
}
export function renderSetlistPanel(root) {
  root.replaceChildren();
  if (!database) return;
  const s = model(), tracks = trackMap(), playlist = current();
  const panel = element("section", "setlist-panel");
  panel.append(element("h2", "setlist-title", "Setlist"));
  const selector = element("select", "setlist-select"); selector.setAttribute("aria-label", t("setlist.choose")); selector.disabled = s.busy;
  for (const p of database.playlists) { const opt = element("option", "", p.name); opt.value = p.id; selector.append(opt); }
  selector.value = playlist.id; selector.addEventListener("change", () => changePlaylist(selector.value)); panel.append(selector);
  const manage = element("div", "setlist-actions");
  manage.append(button(t("setlist.new"), t("setlist.new"), async () => {
    const next = newPlaylist(makeId(), `Playlist ${database.playlists.length + 1}`); database.playlists.push(next); await changePlaylist(next.id);
  }, s.busy));
  manage.append(button(t("setlist.duplicate"), t("setlist.duplicate"), async () => {
    const next = newPlaylist(makeId(), `${playlist.name} (${t("setlist.copy")})`, playlist); database.playlists.push(next); await changePlaylist(next.id);
  }, s.busy)); panel.append(manage);
  const name = element("input", "setlist-name"); name.type = "text"; name.maxLength = 80; name.value = playlist.name;
  name.setAttribute("aria-label", t("setlist.name")); name.disabled = s.busy;
  name.addEventListener("input", () => { playlist.name = name.value.trim() || playlist.name; queueSave(); });
  name.addEventListener("change", () => { playlist.name = name.value.trim() || playlist.name; queueSave(); repaint(); }); panel.append(name);
  panel.append(element("p", "setlist-note", t("setlist.description")));
  panel.append(element("p", "setlist-note", t("setlist.originalControls")));
  const status = element("p", "setlist-status", statusText(s, tracks)); status.setAttribute("role", "status"); panel.append(status);
  const list = element("ol", "setlist-items");
  for (const [index, entry] of playlist.entries.entries()) {
    const track = tracks.get(entry.id), title = track?.title || entry.id;
    const row = element("li", `setlist-item${index === s.index ? " current" : ""}`); row.dataset.id = entry.id;
    const open = button(title, `${t("setlist.openSong")} · ${title}`, () => adjust(playlist, entry), !track || s.status === "loading");
    open.classList.add("setlist-track-open");
    row.classList.toggle("selected", editing?.playlistId === playlist.id && editing?.jobId === entry.id);
    row.append(open, element("span", "setlist-duration", track ? fmtTime(track.duration || 0) : t("setlist.unavailable")));
    const actions = element("div", "setlist-row-actions");
    const move = delta => { const next = [...playlist.entries]; [next[index], next[index + delta]] = [next[index + delta], next[index]]; replaceEntries(next); };
    actions.append(button("↑", `${t("setlist.up")} · ${title}`, () => move(-1), s.busy || index === 0));
    actions.append(button("↓", `${t("setlist.down")} · ${title}`, () => move(1), s.busy || index === s.ids.length - 1));
    actions.append(button("×", `${t("setlist.remove")} · ${title}`, () => replaceEntries(playlist.entries.filter(e => e.id !== entry.id)), s.busy));
    row.append(actions); list.append(row);
  }
  panel.append(list);
  const editingEntry = editing?.playlistId === playlist.id ? playlist.entries.find(e => e.id === editing.jobId) : null;
  panel.append(button(t("setlist.applyAll"), t("setlist.applyAll"), () => {
    applyMixToPlaylist(playlist, editingEntry.mix); queueSave(); repaint();
  }, s.busy || !editingEntry || playlist.entries.length < 2));
  const details = element("details", "setlist-picker"); details.open = s.ids.length === 0;
  details.append(element("summary", "", t("setlist.add")));
  const candidates = [...tracks.values()].filter(track => !s.ids.includes(track.id));
  for (const track of candidates) {
    const label = element("label", "setlist-choice"); const input = document.createElement("input"); input.type = "checkbox"; input.value = track.id; input.disabled = s.busy;
    label.append(input, document.createTextNode(track.title)); details.append(label);
  }
  if (!candidates.length) details.append(element("p", "setlist-note", t("setlist.noCandidates")));
  details.append(button(t("setlist.addSelected"), t("setlist.addSelected"), async () => {
    await flushStoreWrites();
    const selected = [...details.querySelectorAll("input:checked")].map(input => input.value);
    const entries = await Promise.all(selected.map(async id => ({ id, mix: copyMix(await storeGet(`stemdeck:mix:${id}`, {})) })));
    if (entries.length) replaceEntries([...playlist.entries, ...entries]);
  }, s.busy || !candidates.length));
  panel.append(details, element("p", "setlist-note", t("setlist.editHint"))); root.append(panel);
}
