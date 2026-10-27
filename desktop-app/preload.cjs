const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("n3lxAppearance", Object.freeze({
 setTheme(value) { if (["dark", "light", "system"].includes(value)) ipcRenderer.send("n3lx:theme", value); }
}));
