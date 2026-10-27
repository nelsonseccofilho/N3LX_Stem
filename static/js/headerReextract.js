// Compact-header follow-up: non-destructive re-extraction of a finished local track.
// Reuses job.js's existing resplit submit path, so queue, library registration and
// source preservation stay with the code that already owns those operations.
export function initHeaderReextract() {
  const form = document.querySelector("#job-form.header-compact");
  const toggle = form?.querySelector(".import-layout-toggle");
  const submit = form?.querySelector("#submit");
  if (!form || !toggle || !submit) return;
  if (form.querySelector("#reextractCurrentTrack")) return;

  const button = document.createElement("button");
  button.type = "button";
  button.id = "reextractCurrentTrack";
  button.className = "reextract-action";
  button.setAttribute("aria-label", "Extrair novamente a música atual");
  button.textContent = "↻ Reextrair";
  toggle.insertAdjacentElement("afterend", button);

  let lockedFor = "";
  const sync = () => {
    const id = submit.dataset.resplitJob || "";
    const canResplit = /^[a-f0-9]{12}$/i.test(id);
    const staged = Boolean(
      document.getElementById("url")?.value.trim() ||
      document.querySelector(".url-wrap.has-file") ||
      document.getElementById("fileInput")?._files?.length
    );
    const eligible = canResplit && !staged;
    button.disabled = !eligible || lockedFor === id;
    const title = submit.dataset.resplitTitle || "esta música";
    button.title = !canResplit
      ? "Reextração disponível para músicas locais concluídas cuja fonte original foi preservada"
      : staged
        ? "Conclua ou limpe a nova importação antes de reextrair"
        : lockedFor === id
          ? "Reextração solicitada: consulte a fila ou a Biblioteca"
          : `Criar uma nova extração de ${title} sem substituir a versão atual. Usa o modo de separação configurado.`;
  };

  button.addEventListener("click", () => {
    if (button.disabled) return;
    const id = submit.dataset.resplitJob || "";
    if (!/^[a-f0-9]{12}$/i.test(id)) return;
    // Never bypass the existing safe /api/jobs/{id}/resplit flow. Unlike a
    // reimport of a URL, the server gives the copy a unique source identity,
    // preserving the original track and its playlist/folder references.
    lockedFor = id;
    sync();
    try {
      form.requestSubmit(submit);
    } catch (error) {
      lockedFor = "";
      sync();
      console.warn("[reextract] could not submit:", error);
    }
  });

  new MutationObserver(sync).observe(submit, {
    attributes: true,
    attributeFilter: ["data-resplit-job", "data-resplit-title", "data-resplit-source"],
  });
  document.getElementById("url")?.addEventListener("input", sync);
  document.querySelector(".url-wrap") &&
    new MutationObserver(sync).observe(document.querySelector(".url-wrap"), {
      attributes: true, attributeFilter: ["class"],
    });
  document.addEventListener("trackopen", () => {
    lockedFor = "";
    sync();
  });
  sync();
}
