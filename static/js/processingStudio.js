import { getLanguage, onLanguageChange } from "./i18n.js";
import { runningLabel } from "./queue.js";

export const PROCESSING_STATUSES = new Set(["queued", "downloading", "analyzing", "separating", "processing"]);
let selected = null;
const disabledControls = new Map();

export function isProcessingStudio(jobId = null) {
  return !!selected && (jobId == null || selected.job_id === jobId);
}

function render() {
  const panel = document.getElementById("studioProcessing");
  if (!panel || !selected) return;
  const pt = getLanguage().startsWith("pt");
  const pending = PROCESSING_STATUSES.has(selected.status);
  const waiting = selected.status === "queued";
  panel.querySelector("h2").textContent = pending
    ? (waiting ? (pt ? "Música na fila de extração" : "Song queued for extraction") : (pt ? "Preparando suas pistas…" : "Preparing your tracks…"))
    : (pt ? "Extração interrompida" : "Extraction stopped");
  panel.querySelector(".studio-processing-song").textContent = selected.title || (pt ? "Nova música" : "New song");
  panel.querySelector(".studio-processing-detail").textContent = pending
    ? (waiting ? (pt ? "Aguardando a vez de processar." : "Waiting to be processed.") : runningLabel(selected))
    : (selected.error || (pt ? "Nenhuma pista está disponível para reprodução." : "No tracks are available for playback."));
  panel.querySelector(".studio-processing-hint").textContent = pt
    ? "Você pode selecionar e ouvir outra música pronta na biblioteca enquanto isso."
    : "You can select and play another finished song from your library in the meantime.";
  const progress = panel.querySelector("progress");
  progress.hidden = !pending || waiting;
  const fraction = selected.processing ? selected.processing.fraction : selected.progress;
  if (fraction == null || selected.progress_indeterminate) progress.removeAttribute("value");
  else progress.value = Math.max(0, Math.min(1, fraction)) * 100;
  panel.classList.toggle("is-pending", pending);
  panel.setAttribute("aria-busy", String(pending));
}

export function showProcessingStudio(job) {
  selected = { ...job };
  document.querySelector(".app")?.classList.add("is-processing-track");
  const panel = document.getElementById("studioProcessing");
  if (panel) panel.hidden = false;
  for (const id of ["t-play", "t-play-mini", "t-stop", "t-loop", "t-loop-start", "t-loop-end",
    "waveZoomOut", "waveZoomIn", "waveZoomFit", "laneHeightOut", "laneHeightIn"]) {
    const control = document.getElementById(id);
    if (!control) continue;
    if (!disabledControls.has(control)) disabledControls.set(control, control.disabled);
    control.disabled = true;
  }
  render();
}

// A queue frame for another song never changes the selected studio.
export function updateProcessingStudio(job) {
  if (!job || !isProcessingStudio(job.job_id)) return;
  selected = { ...selected, ...job };
  render();
}

export function clearProcessingStudio() {
  selected = null;
  document.querySelector(".app")?.classList.remove("is-processing-track");
  const panel = document.getElementById("studioProcessing");
  if (panel) { panel.hidden = true; panel.removeAttribute("aria-busy"); }
  for (const [control, wasDisabled] of disabledControls) control.disabled = wasDisabled;
  disabledControls.clear();
}

onLanguageChange(render);
