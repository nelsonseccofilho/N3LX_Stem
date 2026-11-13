const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("n3lxAppearance", Object.freeze({
 setTheme(value) { if (["dark", "light", "system"].includes(value)) ipcRenderer.send("n3lx:theme", value); }
}));

contextBridge.exposeInMainWorld("n3lxStorage", Object.freeze({
 getInfo() { return ipcRenderer.invoke("n3lx:storage-info"); },
 chooseExportsFolder() { return ipcRenderer.invoke("n3lx:storage-choose-exports"); }
}));
