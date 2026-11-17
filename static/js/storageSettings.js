// Integrated Storage tab inside Settings. The existing library is never migrated
// by this UI: only-if-empty is checked by the backend as well as by the button.
import { t } from "./i18n.js";

export function wireStorageSettings(overlay) {
  const pane = overlay.querySelector('.settings-pane[data-pane="storage"]');
  const tab = overlay.querySelector('.settings-tab[data-tab="storage"]');
  if (!pane || !tab) return;

  const stemsChange = pane.querySelector("#storageStemsChange");
  const exportsChange = pane.querySelector("#storageExportsChange");
  const stemsPath = pane.querySelector("#storageStemsPath");
  const exportsPath = pane.querySelector("#storageExportsPath");
  const stemsNote = pane.querySelector("#storageStemsNote");
  const exportsNote = pane.querySelector("#storageExportsNote");
  const status = pane.querySelector("#storageSettingsStatus");
  const desktop = () => window.n3lxStorage || null;

  let library = null;
  let updating = false;

  function note(element, key) {
    if (element) element.textContent = t(key);
  }
  function busy(value) {
    updating = value;
    if (stemsChange) stemsChange.disabled = value || !library?.editable ||
      library.busy || library.bytes !== 0 || !desktop()?.chooseStemsFolder;
    if (exportsChange) exportsChange.disabled = value || !desktop()?.chooseExportsFolder;
  }
  async function refresh() {
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

  // Bind only to this settings instance; reopening Settings rebuilds its panes.
  tab.addEventListener("click", () => {
    void refresh().catch(error => {
      console.warn("[storage] load failed:", error);
      note(status, "storage.unavailable");
      busy(false);
    });
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
    // Existing libraries require a separately verified migration. This
    // operation is available only for an empty library, and fails closed.
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
      if (!response.ok || data.persisted !== true) {
        throw new Error(data.detail || "Library change not persisted");
      }
      stemsPath.textContent = data.path;
      note(status, "storage.restart");
      stemsChange.disabled = true; // No second relocation until app restart.
      library = { ...library, editable: false };
    } catch (error) {
      console.warn("[storage] stems folder selection failed:", error);
      note(status, "storage.libraryFailed");
    } finally { busy(false); }
  });
}
