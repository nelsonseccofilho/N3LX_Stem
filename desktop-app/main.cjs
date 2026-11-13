const { app, BrowserWindow, dialog, shell, nativeTheme, ipcMain } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const { createHash } = require("node:crypto");
const packaged = app.isPackaged;
const root = packaged ? path.join(process.resourcesPath, "stemdeck") : path.resolve(__dirname, "..");
const portArg = process.argv.find(x => x.startsWith("--port="));
const port = Number(portArg?.split("=")[1] || (packaged ? 8140 : 8000));
if (!Number.isInteger(port) || port < 1024 || port > 65535) app.exit(1);
const origin = `http://127.0.0.1:${port}`;
let instance = "";
app.setName("N3LX_Stem");
app.setAppUserModelId("N3LX.Stem.Desktop");
if (packaged) app.setPath("userData", process.env.N3LX_STEM_PROFILE_DIR || path.join(app.getPath("appData"), "N3LX_Stem_Release"));
else app.setPath("userData", path.join(root, "data", "desktop"));
fs.mkdirSync(app.getPath("userData"), { recursive: true });
app.commandLine.appendSwitch("lang", "pt-BR");
let win;

// Export preferences live in Electron userData, outside the packaged executable.
// No library, model or audio file is copied or modified by this setting.
function exportsSettingsPath() {
 return path.join(app.getPath("userData"), "storage-preferences.json");
}
function configuredExportsFolder() {
 try {
  const value = JSON.parse(fs.readFileSync(exportsSettingsPath(), "utf8")).exportsFolder;
  return typeof value === "string" && path.isAbsolute(value) ? value : null;
 } catch { return null; }
}
function writableFolder(folder) {
 try {
  return !!folder && fs.statSync(folder).isDirectory() &&
    (fs.accessSync(folder, fs.constants.W_OK), true);
 } catch { return false; }
}
function exportsFolder() {
 const configured = configuredExportsFolder();
 return writableFolder(configured) ? configured : app.getPath("downloads");
}
if (typeof ipcMain.handle === "function") {
 ipcMain.handle("n3lx:storage-info", async event => {
  if (event.sender !== win?.webContents) throw new Error("Unauthorized window");
  const saved = configuredExportsFolder();
  return {
   exportsFolder: saved || app.getPath("downloads"),
   exportsAvailable: !saved || writableFolder(saved),
   configured: Boolean(saved),
  };
 });
 ipcMain.handle("n3lx:storage-choose-exports", async event => {
  if (event.sender !== win?.webContents) throw new Error("Unauthorized window");
  const result = await dialog.showOpenDialog(win, {
   title: "Pasta padrão para exportações do N3LX_Stem",
   properties: ["openDirectory", "createDirectory"],
   defaultPath: exportsFolder(),
  });
  if (result.canceled || !result.filePaths?.[0]) return null;
  const folder = result.filePaths[0];
  if (!writableFolder(folder)) throw new Error("A pasta de exportações deve existir e permitir gravação.");
  const preferences = exportsSettingsPath();
  const temporary = preferences + ".tmp";
  fs.writeFileSync(temporary, JSON.stringify({ exportsFolder: folder }), "utf8");
  fs.renameSync(temporary, preferences);
  return folder;
 });
}
ipcMain.on("n3lx:theme", (event, value) => {
 if (event.sender !== win?.webContents || !["dark", "light", "system"].includes(value)) return;
 nativeTheme.themeSource = value;
 win.setBackgroundColor(nativeTheme.shouldUseDarkColors ? "#0b0f12" : "#f4f6f8");
});
nativeTheme.on("updated", () => { if(win && !win.isDestroyed()) win.setBackgroundColor(nativeTheme.shouldUseDarkColors ? "#0b0f12" : "#f4f6f8"); });
async function health(url = origin) {
  try { const r = await fetch(`${url}/api/health`, { signal: AbortSignal.timeout(2500) }); return r.ok ? await r.json() : null; }
  catch { return null; }
}
async function installation() {
  const file = path.join(app.getPath("userData"), "runtime.json");
  let runtime = process.env.N3LX_STEM_RUNTIME_DIR || (!packaged ? root : "");
  if (!runtime) { try { runtime = JSON.parse(fs.readFileSync(file, "utf8")).runtime; } catch {} }
  const valid = dir => dir && fs.existsSync(path.join(dir, ".venv", "Scripts", "python.exe")) && fs.existsSync(path.join(dir, ".venv-directml", "Scripts", "python.exe"));
  if (!valid(runtime)) {
    const result = await dialog.showOpenDialog({ title: "Selecione a pasta da instalaÃ§Ã£o AMD existente do N3LX_Stem", properties: ["openDirectory"] });
    if (result.canceled) { app.quit(); return null; }
    runtime = result.filePaths[0];
    if (!valid(runtime)) throw new Error("Esta pasta nÃ£o contÃ©m os ambientes do N3LX_Stem. Selecione a instalaÃ§Ã£o AMD existente.");
  }
  if (packaged && !process.env.N3LX_STEM_RUNTIME_DIR) fs.writeFileSync(file, JSON.stringify({ runtime }));
  const data = process.env.N3LX_STEM_DATA_DIR || path.join(runtime, "data");
  // Two servers writing the same library would race. Never stop/adopt the old one.
  if (packaged && !process.env.N3LX_STEM_DATA_DIR && await health("http://127.0.0.1:8000"))
    throw new Error("Feche a outra instÃ¢ncia do N3LX_Stem e seu servidor antes de abrir esta atualizaÃ§Ã£o. Sua biblioteca serÃ¡ mantida.");
  return { runtime, data };
}
async function ensureBackend(config) {
  instance = createHash("sha256").update(JSON.stringify([root, config.runtime, config.data, app.getVersion()])).digest("hex");
  const existing = await health();
  // The existing source launcher can reuse its own backend; release builds require identity.
  if (!packaged && existing?.product === "N3LX_Stem" && existing.status === "ok") return;
  if (existing?.product === "N3LX_Stem" && existing.instance === instance && existing.version === app.getVersion()) return;
  if (existing) throw new Error(`A porta ${port} jÃ¡ estÃ¡ em uso. Feche a outra instÃ¢ncia ou escolha outra porta.`);
  const logs = path.join(config.data, "logs"); fs.mkdirSync(logs, { recursive: true });
  await new Promise((resolve, reject) => {
    const args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path.join(root, "scripts", "Start-N3LX_Stem.ps1"), "-NoBrowser", "-Port", String(port), "-RuntimeRoot", config.runtime, "-DataDir", config.data];
    const child = spawn("powershell.exe", args, { cwd: root, windowsHide: true,
      // Desktop flag is also required for the existing stems-location API.
      // Attach the watchdog to the backend we spawn, never to a foreign process.
      env: { ...process.env, STEMDECK_INSTANCE_TOKEN: instance,
        STEMDECK_DESKTOP: "1", STEMDECK_PARENT_PID: String(process.pid),
        STEMDECK_SETTINGS_MIRROR: path.join(app.getPath("userData"), "settings-mirror.json") } });
    const log = fs.createWriteStream(path.join(logs, "desktop-start.log"), { flags: "a" });
    child.stdout.pipe(log, { end: false }); child.stderr.pipe(log, { end: false });
    const timer = setTimeout(() => { child.kill(); reject(new Error("Tempo de abertura excedido. Consulte o diagnÃ³stico.")); }, 150000);
    child.once("error", error => { clearTimeout(timer); log.end(); reject(error); });
    child.once("exit", code => { clearTimeout(timer); log.end(); code === 0 ? resolve() : reject(new Error("NÃ£o foi possÃ­vel iniciar o N3LX_Stem. Consulte data/logs/desktop-start.log na instalaÃ§Ã£o.")); });
  });
  const ready = await health();
  if (ready?.product !== "N3LX_Stem" || ready.status !== "ok" || ready.instance !== instance) throw new Error("NÃ£o foi possÃ­vel confirmar a identidade do servidor desta atualizaÃ§Ã£o.");
}
function openExternal(url) { try { if (["https:", "http:"].includes(new URL(url).protocol)) shell.openExternal(url); } catch {} }
if (!app.requestSingleInstanceLock()) app.quit();
else {
 app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); } });
 app.whenReady().then(async () => {
   const config = await installation(); if (!config) return;
   await ensureBackend(config);
   win = new BrowserWindow({ title: "N3LX_Stem", width: 1440, height: 960, minWidth: 800, minHeight: 600,
     icon: path.join(root, "desktop", "src-tauri", "icons", "icon.ico"), backgroundColor: "#0a0d10", autoHideMenuBar: true,
     webPreferences: { preload: path.join(__dirname, "preload.cjs"), nodeIntegration: false, contextIsolation: true, sandbox: true } });
   win.webContents.on("page-title-updated", event => { event.preventDefault(); win.setTitle("N3LX_Stem"); });
   win.webContents.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: "deny" }; });
   win.webContents.on("will-navigate", (event, url) => { if (new URL(url).origin !== origin) { event.preventDefault(); openExternal(url); } });
   win.webContents.session.on("will-download", (_event, item) => item.setSaveDialogOptions({ title: "Exportar do N3LX_Stem", defaultPath: path.join(exportsFolder(), path.basename(item.getFilename())) }));
   await win.loadURL(origin);
 }).catch(error => { dialog.showErrorBox("N3LX_Stem nÃ£o pÃ´de abrir", error.message); app.quit(); });
 app.on("window-all-closed", () => app.quit());
}
