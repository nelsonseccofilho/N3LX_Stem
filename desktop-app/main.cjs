const { app, BrowserWindow, dialog, shell } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const portArg = process.argv.find((x) => x.startsWith("--port="));
const port = Number(portArg?.split("=")[1] || 8000);
if (!Number.isInteger(port) || port < 1024 || port > 65535) app.exit(1);
const origin = `http://127.0.0.1:${port}`;
const icon = path.join(root, "desktop", "src-tauri", "icons", "icon.ico");
const logs = path.join(root, "data", "logs");
fs.mkdirSync(logs, { recursive: true });
app.setName("N3LX_Stem");
app.setAppUserModelId("N3LX.Stem.Desktop");
fs.mkdirSync(path.join(root, "data", "desktop"), { recursive: true });
app.setPath("userData", path.join(root, "data", "desktop"));
app.commandLine.appendSwitch("lang", "pt-BR");
let win;

async function healthy() {
  try {
    const response = await fetch(`${origin}/api/health`, { signal: AbortSignal.timeout(2500) });
    const body = await response.json();
    return response.ok && body.product === "N3LX_Stem" && body.status === "ok";
  } catch { return false; }
}

async function ensureBackend() {
  if (await healthy()) return;
  const script = path.join(root, "scripts", "Start-N3LX_Stem.ps1");
  await new Promise((resolve, reject) => {
    const child = spawn("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
      "-NoBrowser", "-Port", String(port)], { cwd: root, windowsHide: true, env: { ...process.env } });
    const log = fs.createWriteStream(path.join(logs, "desktop-start.log"), { flags: "a" });
    child.stdout.pipe(log, { end: false });
    child.stderr.pipe(log, { end: false });
    const timer = setTimeout(() => { child.kill(); reject(new Error("Tempo de abertura excedido.")); }, 150000);
    child.once("error", (err) => { clearTimeout(timer); log.end(); reject(err); });
    child.once("exit", (code) => {
      clearTimeout(timer); log.end();
      if (code === 0) resolve(); else reject(new Error("O servidor não iniciou. Consulte data/logs/desktop-start.log."));
    });
  });
  if (!(await healthy())) throw new Error("N3LX_Stem não respondeu no endereço local.");
}

function openExternal(url) {
  try { if (["https:", "http:"].includes(new URL(url).protocol)) shell.openExternal(url); } catch {}
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); } });
  app.whenReady().then(async () => {
    await ensureBackend();
    fs.writeFileSync(path.join(logs, "desktop.pid"), String(process.pid));
    win = new BrowserWindow({ title: "N3LX_Stem", width: 1440, height: 960,
      minWidth: 1080, minHeight: 720, icon, backgroundColor: "#0a0d10", autoHideMenuBar: true,
      webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true } });
    win.setAppDetails({ appId: "N3LX.Stem.Desktop", appIconPath: icon,
      relaunchCommand: `"${process.execPath}" "${__dirname}" --port=${port}`,
      relaunchDisplayName: "N3LX_Stem" });
    win.webContents.on("page-title-updated", (event) => { event.preventDefault(); win.setTitle("N3LX_Stem"); });
    win.webContents.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: "deny" }; });
    win.webContents.on("will-navigate", (event, url) => {
      if (new URL(url).origin !== origin) { event.preventDefault(); openExternal(url); }
    });
    win.webContents.session.on("will-download", (_event, item) => {
      item.setSaveDialogOptions({ title: "Exportar do N3LX_Stem", defaultPath: path.join(app.getPath("downloads"), item.getFilename()) });
    });
    await win.loadURL(origin);
  }).catch((error) => {
    dialog.showErrorBox("N3LX_Stem não pôde abrir", error.message);
    app.quit();
  });
  app.on("window-all-closed", () => app.quit());
  app.on("will-quit", () => {
    const pidFile = path.join(logs, "desktop.pid");
    try { if (fs.readFileSync(pidFile, "utf8").trim() === String(process.pid)) fs.unlinkSync(pidFile); } catch {}
  });
}
