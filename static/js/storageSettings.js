// Dedicated desktop storage settings: source/library and exports are independent.
// Never start a migration of an existing library from this UI.
import { t } from "./i18n.js";

const dialog = document.getElementById("storageSettingsDialog");
const open = document.getElementById("settingsBtn");
const close = document.getElementById("storageSettingsClose");
const stemsChange = document.getElementById("storageStemsChange");
const exportsChange = document.getElementById("storageExportsChange");
const stemsPath = document.getElementById("storageStemsPath");
const exportsPath = document.getElementById("storageExportsPath");
const stemsNote = document.getElementById("storageStemsNote");
const exportsNote = document.getElementById("storageExportsNote");
const status = document.getElementById("storageSettingsStatus");

const desktop = () => window.n3lxStorage || null;
let library = null;
let updating = false;
function note(element, key) {
  if (element) element.textContent = t(key);
}
function busy(value) {
  updating = value;
  if (stemsChange) stemsChange.disabled = value || !library?.editable || library.busy ||
    library.bytes !== 0 || !desktop()?.chooseStemsFolder;
  if (exportsChange) exportsChange.disabled = value || !desktop()?.chooseExportsFolder;
}
async function refresh() {
  if (!dialog) return;
  busy(true);
  status.textContent = "";
  const [libraryResponse, exportsResponse] = await Promise.allSettled([
    fetch("/api/settings/stems-location", { cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Library status " + response.status);
        return response.json();
      }),
    desktop()?.getInfo?.() ?? Promise.resolve(null),
  ]);
  library = libraryResponse.status === "fulfilled" ? libraryResponse.value : null;
  stemsPath.textContent = library?.path || "—";
  exportsPath.textContent = exportsResponse.status === "fulfilled"
    ? exportsResponse.value?.exportsFolder || "—" : "—";

  if (!desktop()) {
    note(stemsNote, "storage.desktopOnly");
    note(exportsNote, "storage.desktopOnly");
  } else if (!library) {
    note(stemsNote, "storage.unavailable");
  } else if (!library.editable) {
    note(stemsNote, "storage.notEditable");
  } else if (library.bytes > 0) {
    note(stemsNote, "storage.migrationPending");
  } else if (library.busy) {
    note(stemsNote, "storage.busy");
  } else {
    note(stemsNote, "storage.emptyLibrary");
  }
  if (desktop()) {
    if (exportsResponse.status === "rejected") {
      note(exportsNote, "storage.unavailable");
    } else {
      note(exportsNote, exportsResponse.value?.exportsAvailable === false
        ? "storage.exportsOffline" : "storage.exportsReady");
    }
  }
  busy(false);
}

open?.addEventListener("click", () => {
  if (!dialog?.showModal) return;
  dialog.showModal();
  void refresh().catch(error => { console.warn("[storage] load failed:", error); note(status, "storage.unavailable"); busy(false); });
});
close?.addEventListener("click", () => dialog?.close());
dialog?.addEventListener("click", event => {
  if (event.target === dialog) dialog.close();
});

exportsChange?.addEventListener("click", async () => {
  if (updating || !desktop()?.chooseExportsFolder) return;
  busy(true);
  try {
    const picked = await desktop().chooseExportsFolder();
    if (picked) {
      exportsPath.textContent = picked;
      note(status, "storage.exportsSaved");
    }
  } catch (error) {
    console.warn("[storage] export folder selection failed:", error);
    note(status, "storage.unavailable");
  } finally { busy(false); }
});

stemsChange?.addEventListener("click", async () => {
  // Existing libraries must be migrated and verified as a separate, approved
  // operation. This path is only available to a genuinely empty new library.
  if (updating || !library?.editable || library.bytes !== 0 || library.busy ||
      !desktop()?.chooseStemsFolder) return;
  busy(true);
  try {
    const folder = await desktop().chooseStemsFolder();
    if (!folder) return;
    if (!window.confirm(t("storage.confirmEmpty"))) return;
    const response = await fetch("/api/settings/stems-location", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: folder, only_if_source_empty: true }),
    });
    const data = await response.json();
    if (!response.ok || data.persisted !== true) throw new Error(data.detail || "Library change not persisted");
    stemsPath.textContent = data.path;
    note(status, "storage.restart");
    stemsChange.disabled = true; // No second relocation until app restart.
    library = { ...library, editable: false };
  } catch (error) {
    console.warn("[storage] stems folder selection failed:", error);
    note(status, "storage.libraryFailed");
  } finally { busy(false); }
});
