import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { EventEmitter } from "node:events";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import test from "node:test";

// Execute the real Electron entry point with inert OS/Electron doubles.
// No server, library, window, GPU or process is actually started.
const entry = fs.readFileSync(new URL("../../desktop-app/main.cjs", import.meta.url), "utf8");

async function launch({ existingBackend = null } = {}) {
  const pid = 48321;
  const resourcesPath = path.join("C:", "N3LX-Test", "resources");
  const runtime = path.join("C:", "N3LX-Test", "runtime");
  const data = path.join("C:", "N3LX-Test", "qa-data");
  const version = "0.21.0-rc.10";
  const root = path.join(resourcesPath, "stemdeck");
  const expectedInstance = createHash("sha256")
    .update(JSON.stringify([root, runtime, data, version])).digest("hex");
  let envUsed = null;
  let spawnCount = 0;
  let dialogError = "";
  let appQuitCount = 0;
  let resolveDone;
  const done = new Promise(resolve => { resolveDone = resolve; });

  const app = {
    isPackaged: true,
    setName() {},
    setAppUserModelId() {},
    setPath() {},
    getPath(name) { return name === "downloads" ? "C:\\Downloads" : "C:\\AppData"; },
    getVersion() { return version; },
    commandLine: { appendSwitch() {} },
    requestSingleInstanceLock() { return true; },
    whenReady() { return Promise.resolve(); },
    on() {},
    quit() { appQuitCount += 1; resolveDone(); },
  };
  class FakeWindow {
    constructor() {
      this.webContents = {
        on() {},
        setWindowOpenHandler() {},
        session: { on() {} },
      };
    }
    setBackgroundColor() {}
    loadURL() { resolveDone(); return Promise.resolve(); }
  }
  const fakes = {
    electron: {
      app, BrowserWindow: FakeWindow,
      dialog: { showErrorBox(_title, message) { dialogError = message; } },
      shell: { openExternal() {} },
      nativeTheme: { on() {}, shouldUseDarkColors: false },
      ipcMain: { on() {} },
    },
    fs: {
      mkdirSync() {},
      existsSync(filename) {
        return /[\\/]\.venv(?:-directml)?[\\/]Scripts[\\/]python\.exe$/.test(filename);
      },
      createWriteStream() { return { end() {} }; },
    },
    child_process: {
      spawn(_exe, _args, options) {
        spawnCount++;
        envUsed = options.env;
        const child = new EventEmitter();
        child.stdout = { pipe() {} };
        child.stderr = { pipe() {} };
        child.kill = () => { throw new Error("Unexpected forced termination"); };
        queueMicrotask(() => child.emit("exit", 0));
        return child;
      },
    },
  };
  const fakeProcess = {
    pid, argv: ["N3LX_Stem.exe", "--port=8159"], resourcesPath,
    env: {
      N3LX_STEM_RUNTIME_DIR: runtime,
      N3LX_STEM_DATA_DIR: data,
      N3LX_STEM_PROFILE_DIR: "C:\\QAProfile",
    },
  };
  const request = async url => {
    if (url.includes(":8000/")) return { ok: false };
    const health = existingBackend ||
      (envUsed ? {
        product: "N3LX_Stem", status: "ok", version,
        instance: envUsed.STEMDECK_INSTANCE_TOKEN,
      } : null);
    return health ? { ok: true, json: async () => health } : { ok: false };
  };
  vm.runInNewContext(entry, {
    require(name) {
      if (name === "electron") return fakes.electron;
      if (name === "node:fs") return fakes.fs;
      if (name === "node:child_process") return { spawn: fakes.child_process.spawn };
      if (name === "node:path") return path;
      if (name === "node:crypto") return { createHash };
      throw new Error("Unexpected module: " + name);
    },
    process: fakeProcess,
    fetch: request,
    AbortSignal: { timeout() { return {}; } },
    setTimeout, clearTimeout, URL,
  }, { filename: "desktop-app/main.cjs" });
  await Promise.race([
    done,
    new Promise((_resolve, reject) => setTimeout(() => reject(new Error("Desktop launch test timed out")), 2000)),
  ]);
  return { pid, envUsed, expectedInstance, spawnCount, dialogError, appQuitCount };
}

test("new packaged backend inherits Electron parent identity and watchdog flag", async () => {
  const result = await launch();
  assert.equal(result.spawnCount, 1);
  assert.equal(result.envUsed.STEMDECK_DESKTOP, "1");
  assert.equal(result.envUsed.STEMDECK_PARENT_PID, String(result.pid));
  assert.equal(result.envUsed.STEMDECK_INSTANCE_TOKEN, result.expectedInstance);
  assert.equal(result.dialogError, "");
  assert.equal(result.appQuitCount, 0);
});

test("foreign backend occupying port is not stopped or adopted", async () => {
  const result = await launch({ existingBackend: {
    product: "N3LX_Stem", status: "ok", version: "0.21.0-rc.8",
    instance: "different-owner",
  } });
  assert.equal(result.spawnCount, 0);
  assert.equal(result.envUsed, null);
  assert.equal(result.appQuitCount, 1);
  assert.match(result.dialogError, /8140|8159|already|j[aá] est[aá]/i);
});
