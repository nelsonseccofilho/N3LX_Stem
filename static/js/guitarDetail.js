import { t } from "./i18n.js";
import { reloadCurrentTrack } from "./catalog.js";
import { getMixerReloadContext, prepareGuitarMix } from "./mixer.js";

const busyStates = new Set(["queued", "running", "cancelling"]);
const node = (tag, text) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
};
const time = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

export function guitarProgress(value, translate = t) {
  if (!value) return "";
  if (value.status !== "running") return translate(`guitar.status.${value.status}`);
  const progress = value.progress || {};
  const phase = translate(`guitar.phase.${progress.phase || "loading"}`);
  const position = progress.chunk ? translate("guitar.chunk", { chunk: progress.chunk, chunks: progress.chunks }) : "";
  const role = progress.role ? translate(`guitar.role.${progress.role}`) : "";
  return [role, position, phase, time(value.elapsed || 0)].filter(Boolean).join(" · ");
}

export function openGuitarDetail(song, trigger) {
  const dialog = node("dialog"); dialog.className = "song-organize-dialog guitar-detail-dialog";
  const content = node("div"); content.className = "song-organize-form";
  const heading = node("h2", t("guitar.title")); heading.id = "guitar-detail-title";
  dialog.setAttribute("aria-labelledby", heading.id);
  content.append(heading, node("p", song.title), node("p", t("guitar.notice")));
  const choices = node("fieldset"); choices.append(node("legend", t("guitar.select")));
  const roles = ["lead", "acoustic", "rhythm"].map(role => {
    const label = node("label"); const input = node("input"); input.type = "checkbox"; input.value = role; input.checked = true;
    label.append(input, document.createTextNode(t(`guitar.role.${role}`))); choices.append(label); return input;
  });
  content.append(choices, node("p", t("guitar.order")));
  const status = node("p"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  const progress = node("progress"); progress.max = 100; progress.setAttribute("aria-label", t("guitar.completed"));
  const completed = node("p"); completed.className = "guitar-progress-count";
  const error = node("p"); error.className = "song-dialog-error"; error.setAttribute("role", "alert");
  content.append(status, progress, completed, error);
  const actions = node("div"); actions.className = "song-dialog-actions";
  const addButton = (label, action) => {
    const button = node("button", t(label)); button.type = "button"; button.addEventListener("click", action); actions.append(button); return button;
  };
  let state = null, pending = false, timer = null, closed = false, revision = 0, hydrated = false;
  const abort = new AbortController();
  const generate = addButton("guitar.generate", () => mutate("", { roles: roles.filter(input => input.checked).map(input => input.value) }));
  generate.className = "song-primary";
  const cancel = addButton("guitar.cancel", () => mutate("/cancel"));
  const apply = addButton("guitar.apply", () => switchTracks("apply"));
  const restore = addButton("guitar.original", () => switchTracks("original"));
  const refresh = addButton("guitar.refresh", () => update());
  const closeButton = addButton("guitar.close", () => dialog.close());
  function render() {
    const busy = busyStates.has(state?.status);
    choices.disabled = pending || busy || state?.applied;
    generate.disabled = pending || !state?.available || busy || state?.applied || !roles.some(input => input.checked);
    cancel.hidden = !busy; cancel.disabled = pending || state?.status === "cancelling";
    apply.hidden = !state?.result_available || state?.applied; apply.disabled = pending || busy;
    restore.hidden = !state?.applied; restore.disabled = pending || busy;
    refresh.disabled = pending;
    closeButton.disabled = pending;
    status.textContent = !state ? t("guitar.loading") : !state.available ? t("guitar.unavailable") : state.applied ? t("guitar.applied") : guitarProgress(state);
    progress.hidden = !busy;
    const percentage = Number(state?.progress?.percent);
    if (Number.isFinite(percentage)) progress.value = Math.max(0, Math.min(100, percentage));
    else progress.removeAttribute("value");
    const p = state?.progress || {};
    completed.textContent = busy && p.total_chunks ? t("guitar.completedCount", { completed: p.completed_chunks || 0, total: p.total_chunks }) : "";
    if (state?.error) error.textContent = state.error;
  }
  roles.forEach(input => input.addEventListener("change", render));
  async function request(suffix = "", body) {
    const response = await fetch(`/api/jobs/${encodeURIComponent(song.id)}/guitar-detail${suffix}`, {
      ...(body !== undefined ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}), signal: abort.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : t("guitar.failed"));
    return result;
  }
  function schedule() {
    clearTimeout(timer);
    if (!closed && busyStates.has(state?.status)) timer = setTimeout(update, 1200);
  }
  async function update() {
    if (closed || pending) return;
    const version = revision;
    try {
      const next = await request();
      if (closed || version !== revision) return;
      state = next;
      if (!hydrated && state.roles?.length) roles.forEach(input => { input.checked = state.roles.includes(input.value); });
      hydrated = true; error.textContent = ""; render(); schedule();
    }
    catch (problem) { if (!closed) { error.textContent = problem.message; render(); } }
  }
  async function mutate(suffix, body = {}) {
    revision++; pending = true; clearTimeout(timer); error.textContent = ""; render();
    try { state = await request(suffix, body); }
    catch (problem) { if (!closed) error.textContent = problem.message; }
    finally { pending = false; if (!closed) { render(); schedule(); } }
  }
  async function switchTracks(action) {
    revision++; pending = true; clearTimeout(timer); error.textContent = ""; render();
    try {
      state = await request(`/${action}`, {});
      await prepareGuitarMix(song.id, action === "apply" ? state.result?.names || [] : []);
      const context = getMixerReloadContext(song.id);
      dialog.close();
      await reloadCurrentTrack(song.id, context);
    } catch (problem) { if (!closed) error.textContent = problem.message; }
    finally { pending = false; if (!closed) { render(); schedule(); } }
  }
  const closeForTrack = () => dialog.close();
  dialog.addEventListener("cancel", event => { if (pending) event.preventDefault(); });
  document.addEventListener("trackwillopen", closeForTrack);
  dialog.addEventListener("close", () => {
    closed = true; clearTimeout(timer); abort.abort(); document.removeEventListener("trackwillopen", closeForTrack);
    dialog.remove(); trigger?.focus();
  }, { once: true });
  content.append(actions); dialog.append(content); document.body.append(dialog); render(); dialog.showModal(); update();
}
