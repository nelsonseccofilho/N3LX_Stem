import { getLanguage, onLanguageChange } from "./i18n.js";
import { onQueueChange, getQueueSnapshot, cancelQueuedJob } from "./queue.js";

const labels = {
  pt: { prepare: "Preparar áudio", analyze: "Analisar música", separate: "Separar instrumentos", vocals: "Separar vozes", guitars: "Detalhar guitarras", drums: "Detalhar bateria", reconstruct: "Preservar resíduos", finalize: "Finalizar pistas" },
  en: { prepare: "Prepare audio", analyze: "Analyze song", separate: "Separate instruments", vocals: "Separate vocals", guitars: "Detail guitars", drums: "Detail drums", reconstruct: "Preserve residues", finalize: "Finalize tracks" },
};
const isPt = () => getLanguage().startsWith("pt");
export function stepLabel(id) { return (isPt() ? labels.pt : labels.en)[id] || id; }
export function clock(seconds) {
  const n = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(n / 60).toString().padStart(2, "0")}:${(n % 60).toString().padStart(2, "0")}`;
}
export function processingLabel(job) {
  const p = job?.processing;
  if (!p) return null;
  const prefix = isPt() ? `Etapa ${p.step_number} de ${p.total_steps}` : `Step ${p.step_number} of ${p.total_steps}`;
  const pct = p.fraction == null ? "" : ` · ${Math.floor(p.fraction * 100)}%`;
  return `${prefix} · ${stepLabel(p.step)}${pct}`;
}

let current = null;
let timer = null;
let lastJob = null;
let revision = 0;
let dismissed = null;
let selectedId = null;

function withProgress(job) {
  if (job.processing) return job;
  const now = Date.now() / 1000;
  const ids = job.separation_profile === "standard" ? ["prepare","analyze","separate","finalize"] : Object.keys(labels.en);
  return { ...job, processing: { step:"prepare", step_number:1, total_steps:ids.length,
    completed_steps:0, fraction:null, terminal:false, started_at:now, step_started_at:now,
    steps:ids.map(id => ({ id, state:"pending" })) } };
}

function render() {
  const panel = document.getElementById("processingPanel");
  if (!panel) return;
  const p = current?.processing;
  const visible = p && current.job_id !== dismissed;
  panel.hidden = !visible;
  panel.setAttribute("data-active", String(Boolean(visible && !p.terminal)));
  if (!visible) return;
  const pt = isPt();
  const terminal = p.terminal;
  const done = current.status === "done";
  const waiting = current.status === "queued";
  const status = done ? (pt ? "Extração concluída" : "Extraction complete") :
    terminal ? (pt ? "Extração interrompida" : "Extraction stopped") :
    waiting ? (pt ? "Aguardando extração" : "Waiting for extraction") : (pt ? "Extraindo" : "Extracting");
  panel.querySelector(".processing-title").textContent = `${status} · ${current.title || "Áudio"}`;
  panel.querySelector(".processing-current").textContent = done ?
    (pt ? "Pistas prontas na biblioteca" : "Tracks ready in your library") : processingLabel(current);
  const now = Date.now() / 1000;
  const elapsed = waiting ? 0 : terminal ? p.elapsed_seconds : now - p.started_at;
  const stepElapsed = waiting ? 0 : terminal ? p.step_elapsed_seconds : now - p.step_started_at;
  const actualDevice = p.device || (p.step === "vocals" ? "cpu" : p.step === "separate" ? current.compute_device : "");
  const device = actualDevice === "directml" ? "AMD / DirectML" : actualDevice === "cpu" ? "CPU" : actualDevice || "";
  panel.querySelector(".processing-time").textContent = pt ?
    `Total ${clock(elapsed)} · Nesta etapa ${clock(stepElapsed)}${device ? ` · ${device}` : ""}` :
    `Total ${clock(elapsed)} · This step ${clock(stepElapsed)}${device ? ` · ${device}` : ""}`;
  const bar = panel.querySelector("progress");
  if (p.fraction == null) bar.removeAttribute("value");
  else bar.value = p.fraction * 100;
  const counters = p.counters;
  let note = pt ? "Em andamento · esta parte não informa percentual." : "In progress · this part does not report a percentage.";
  if (waiting) note = pt ? "Aguardando sua vez na fila." : "Waiting for its turn in the queue.";
  if (counters?.total) note = pt ? `Processamento: passagem ${counters.pass}/${counters.passes} · ${counters.completed}/${counters.total} trechos. Depois, as pistas serão gravadas.` :
    `Processing: pass ${counters.pass}/${counters.passes} · ${counters.completed}/${counters.total} chunks. The tracks will then be written.`;
  if (terminal) note = done ? (pt ? "Você já pode abrir o resultado e exportar as pistas." : "Open the result to play or export the tracks.") : current.error || (pt ? "O processamento foi encerrado." : "Processing has stopped.");
  panel.querySelector(".processing-note").textContent = note;
  panel.querySelector(".processing-completed").textContent = pt ? `${p.completed_steps} de ${p.total_steps} etapas concluídas` : `${p.completed_steps} of ${p.total_steps} steps complete`;
  const list = panel.querySelector(".processing-steps");
  if (list.children.length !== p.steps.length) {
    list.replaceChildren(...p.steps.map(() => {
      const li = document.createElement("li");
      const icon = document.createElement("span"); icon.className = "processing-number";
      const text = document.createElement("span"); text.className = "processing-step-name";
      const status = document.createElement("span"); status.className = "processing-step-state";
      li.append(icon, text, status); return li;
    }));
  }
  p.steps.forEach((step, i) => {
    const el = list.children[i];
    el.className = `processing-step ${step.state}`;
    el.querySelector(".processing-number").textContent = step.state === "done" ? "✓" : step.state === "warning" ? "!" : String(i + 1);
    el.querySelector(".processing-step-name").textContent = stepLabel(step.id);
    el.querySelector(".processing-step-state").textContent = step.state === "done" ? (pt ? "Concluída" : "Complete") : step.state === "warning" ? (pt ? "Com aviso" : "Warning") : step.state === "running" ? (p.fraction == null ? (pt ? "Em andamento" : "In progress") : `${Math.floor(p.fraction * 100)}%`) : (pt ? "Na sequência" : "Next");
    if (step.state === "running") el.setAttribute("aria-current", "step"); else el.removeAttribute("aria-current");
  });
  const cancel = panel.querySelector(".processing-cancel");
  cancel.hidden = terminal;
  cancel.textContent = pt ? "Cancelar extração" : "Cancel extraction";
  cancel.disabled = !!current.cancel_requested;
  const close = panel.querySelector(".processing-close"); close.hidden = !terminal;
  close.textContent = pt ? "Fechar aviso" : "Dismiss";
}

async function queueChanged(snap) {
  const rev = ++revision;
  const chosen = snap.running?.job_id === selectedId ? snap.running : snap.queued?.find(job => job.job_id === selectedId) || snap.running;
  if (chosen) {
    current = withProgress(chosen);
    lastJob = current.job_id;
    render();
    if (!timer) timer = setInterval(render, 1000);
    return;
  }
  clearInterval(timer); timer = null;
  if (lastJob) {
    const id = lastJob; lastJob = null;
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
      if (response.ok && rev === revision) {
        const final = await response.json();
        if (rev !== revision) return;
        current = final; render(); return;
      }
    } catch (error) { console.warn("[progress] final state unavailable", error); }
  }
  if (rev === revision && !current?.processing?.terminal) { current = null; render(); }
}

export function initProcessingProgress() {
  document.querySelector(".processing-cancel")?.addEventListener("click", async () => {
    if (!current || current.processing?.terminal) return;
    const id = current.job_id;
    document.querySelector(".processing-cancel").disabled = true;
    await cancelQueuedJob(id);
  });
  document.querySelector(".processing-close")?.addEventListener("click", () => { dismissed = current?.job_id; render(); });
  onQueueChange(queueChanged);
  document.addEventListener("trackwillopen", event => {
    selectedId = event.detail?.source === "processing" ? event.detail.jobId : null;
    queueChanged(getQueueSnapshot());
  });
  onLanguageChange(render);
  queueChanged(getQueueSnapshot());
}
