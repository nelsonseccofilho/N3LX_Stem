import { t, onLanguageChange } from "./i18n.js";

// Delegate submission to the existing non-destructive resplit flow.
export function initHeaderReextract() {
  const form = document.querySelector("#job-form.header-compact");
  const toggle = form?.querySelector(".import-layout-toggle");
  const submit = form?.querySelector("#submit");
  if (!form || !toggle || !submit || form.querySelector("#reextractCurrentTrack")) return;
  const button = document.createElement("button");
  button.type = "button";
  button.id = "reextractCurrentTrack";
  button.className = "reextract-action";
  toggle.insertAdjacentElement("afterend", button);
  const sync = () => {
    const id = submit.dataset.resplitJob || "";
    const valid = /^[a-f0-9]{12}$/i.test(id);
    const picker = document.getElementById("fileInput");
    const staged = Boolean(document.getElementById("url")?.value.trim() ||
      document.querySelector(".url-wrap.has-file") || picker?._file || picker?._files?.length || picker?.files?.length);
    const pending = submit.classList.contains("loading");
    button.textContent = t("reextract.action");
    button.setAttribute("aria-label", t("reextract.aria"));
    button.disabled = !valid || staged || submit.disabled || pending;
    button.setAttribute("aria-busy", String(pending));
    button.title = t(!valid ? "reextract.unavailable" : staged ? "reextract.staged" : pending ? "reextract.pending" : "reextract.ready", { title: submit.dataset.resplitTitle || "♪" });
  };
  button.addEventListener("click", () => {
    if (!button.disabled) form.requestSubmit(submit);
  });
  new MutationObserver(sync).observe(submit, { attributes: true,
    attributeFilter: ["data-resplit-job", "data-resplit-title", "data-resplit-source", "disabled", "class"] });
  document.getElementById("url")?.addEventListener("input", sync);
  document.getElementById("fileInput")?.addEventListener("change", sync);
  const wrap = document.querySelector(".url-wrap");
  if (wrap) new MutationObserver(sync).observe(wrap, { attributes: true, attributeFilter: ["class"] });
  document.addEventListener("trackopen", sync);
  onLanguageChange(sync);
  sync();
}
