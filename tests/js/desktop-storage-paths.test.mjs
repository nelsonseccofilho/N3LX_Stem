import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import test from "node:test";
import { fileURLToPath } from "node:url";

const entryPath = fileURLToPath(new URL("../../desktop-app/main.cjs", import.meta.url));
const entry = fs.readFileSync(entryPath, "utf8");

test("Electron keeps exports outside package, persists choice and enables desktop backend", async () => {
  const runtime = path.resolve("test-runtime");
  const profile = path.resolve("test-profile");
  const data = path.resolve("test-runtime-data");
  const selected = path.resolve("test-exports");
  const registered = new Map();
  const events = new Map();
  const memory = new Map();
  let window = null;
  let launchedEnv = null;
  let complete;
  const loaded = new Promise(resolve => { complete = resolve; });
  const fakeApp = {
    isPackaged: true,
    setName() {}, setAppUserModelId() {}, commandLine: { appendSwitch() {} },
    setPath(name, value) { if (name === "userData") this.profile = value; },
    getPath(name) {
      if (name === "userData") return this.profile || profile;
      return name === "downloads" ? path.resolve("test-downloads") : profile;
    },
    getVersion() { return "0.21.0-rc.10"; },
    requestSingleInstanceLock() { return true; },
    whenReady() { return Promise.resolve(); }, on() {}, quit() {},
  };
  class FakeWindow {
    constructor() {
      this.webContents = {
        on() {}, setWindowOpenHandler() {},
        session: { on(name, fn) { events.set(name, fn); } },
      };
      window = this;
    }
    setBackgroundColor() {}
    loadURL() { complete(); return Promise.resolve(); }
  }
  const fakeFs = {
    mkdirSync() {}, createWriteStream() { return { end() {} }; },
    constants: { W_OK: 2 },
    existsSync(filename) {
      return /[\\/]\.venv(?:-directml)?[\\/]Scripts[\\/]python\.exe$/.test(filename);
    },
    statSync(filename) {
      if (filename !== selected) throw new Error("Missing directory");
      return { isDirectory: () => true };
    },
    accessSync(folder) { if (folder !== selected) throw new Error("Unavailable"); },
    readFileSync(filename) {
      if (!memory.has(filename)) throw new Error("ENOENT");
      return memory.get(filename);
    },
    writeFileSync(filename, data) { memory.set(filename, data); },
    renameSync(from, to) {
      memory.set(to, memory.get(from)); memory.delete(from);
    },
  };
  const launch = {
    electron: {
      app: fakeApp, BrowserWindow: FakeWindow,
      dialog: {
        showOpenDialog: async () => ({ canceled: false, filePaths: [selected] }),
        showErrorBox(_title, error) { throw new Error(error); },
      },
      shell: { openExternal() {} },
      nativeTheme: { on() {}, shouldUseDarkColors: false },
      ipcMain: {
        on() {},
        handle(name, callback) { registered.set(name, callback); },
      },
    },
    fs: fakeFs,
    child_process: {
      spawn(_exe, _args, opts) {
        launchedEnv = opts.env;
        const child = new EventEmitter();
        child.stdout = { pipe() {} };
        child.stderr = { pipe() {} };
        queueMicrotask(() => child.emit("exit", 0));
        return child;
      },
    },
  };
  const hash = createHash; // included to match the real desktop boot path.
  vm.runInNewContext(entry, {
    // Match the CommonJS module wrapper used by Electron/Node.
    __dirname: path.dirname(entryPath),
    require(name) {
      if (name === "electron") return launch.electron;
      if (name === "node:fs") return launch.fs;
      if (name === "node:child_process") return launch.child_process;
      if (name === "node:path") return path;
      if (name === "node:crypto") return { createHash: hash };
      throw new Error("Unexpected dependency: " + name);
    },
    process: {
      argv: ["N3LX_Stem.exe", "--port=8159"], pid: 12345,
      resourcesPath: path.resolve("test-package", "resources"),
      env: {
        N3LX_STEM_RUNTIME_DIR: runtime,
        N3LX_STEM_DATA_DIR: data,
        N3LX_STEM_PROFILE_DIR: profile,
      },
    },
    fetch: async url => {
      if (url.includes(":8000/")) return { ok: false };
      return launchedEnv
        ? { ok: true, json: async () => ({ product: "N3LX_Stem", status: "ok",
            version: "0.21.0-rc.10", instance: launchedEnv.STEMDECK_INSTANCE_TOKEN }) }
        : { ok: false };
    },
    AbortSignal: { timeout() { return {}; } },
    setTimeout, clearTimeout, URL,
  }, { filename: "desktop-app/main.cjs" });
  await Promise.race([
    loaded,
    new Promise((_, reject) => setTimeout(() => reject(new Error("Desktop boot timeout")), 2000)),
  ]);
  assert.equal(launchedEnv.STEMDECK_DESKTOP, "1");
  assert.equal(launchedEnv.STEMDECK_PARENT_PID, "12345");
  assert.equal(launchedEnv.STEMDECK_SETTINGS_MIRROR,
    path.join(profile, "settings-mirror.json"));

  const sender = { sender: window.webContents };
  const before = await registered.get("n3lx:storage-info")(sender);
  assert.equal(before.configured, false);
  assert.equal(await registered.get("n3lx:storage-choose-exports")(sender), selected);
  const after = await registered.get("n3lx:storage-info")(sender);
  assert.equal(after.exportsFolder, selected);
  assert.equal(after.exportsAvailable, true);
  const item = {
    getFilename() { return "vocals.wav"; },
    setSaveDialogOptions(value) { this.options = value; },
  };
  events.get("will-download")({}, item);
  assert.equal(item.options.defaultPath, path.join(selected, "vocals.wav"));

  await assert.rejects(
    registered.get("n3lx:storage-choose-exports")({ sender: {} }),
    /Unauthorized window/,
  );
});

test("Storage appears as the second native Settings tab, without a second modal", () => {
  const catalog = fs.readFileSync(
    path.resolve(path.dirname(entryPath), "../static/js/catalog.js"), "utf8"
  );
  const html = fs.readFileSync(
    path.resolve(path.dirname(entryPath), "../static/index.html"), "utf8"
  );
  const storage = fs.readFileSync(
    path.resolve(path.dirname(entryPath), "../static/js/storageSettings.js"), "utf8"
  );

  const general = catalog.indexOf('data-tab="general"');
  const storageTab = catalog.indexOf('data-tab="storage"');
  const details = catalog.indexOf('data-tab="details"');
  assert.ok(general >= 0 && general < storageTab && storageTab < details);
  assert.match(catalog, /data-pane="storage"/);
  assert.match(catalog, /wireStorageSettings\(overlay\)/);
  assert.match(catalog, /id="storageExportsChange"/);
  assert.match(catalog, /id="storageStemsChange"[^>]*disabled/);
  assert.doesNotMatch(html, /storageSettingsDialog|src="\/js\/storageSettings\.js"/);
  assert.match(storage, /export function wireStorageSettings\(overlay\)/);
  assert.match(storage, /only_if_source_empty: true/);
  assert.doesNotMatch(storage, /showModal\(/);
});
