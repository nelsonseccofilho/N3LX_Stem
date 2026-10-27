import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const code = readFileSync(new URL("../../static/js/theme.js", import.meta.url), "utf8").replace(/^import .*;\r?\n/gm, "").replace(/^export /gm, "");
const writes = [], root = { dataset: {}, style: {} }, native = [];
let change;
const media = { matches: false, addEventListener: (_, fn) => { change = fn; } };
const context = vm.createContext({ document: { documentElement: root, dispatchEvent() {} },
 window: { matchMedia: () => media, dispatchEvent() {}, n3lxAppearance: { setTheme: p => native.push(p) } },
 Event: class {}, CustomEvent: class {}, storeGet: async () => null, storeSet: async (...args) => writes.push(args) });
vm.runInContext(code + "\nglobalThis.api={initTheme,setTheme,getTheme};", context);
await context.api.initTheme();
assert.equal(root.dataset.theme, "light"); assert.equal(context.api.getTheme(), "system");
media.matches = true; change(); assert.equal(root.dataset.theme, "dark");
await context.api.setTheme("light"); change(); assert.equal(root.dataset.theme, "light");
assert.equal(writes.at(-1)[0], "stemdeck.theme"); assert.equal(writes.at(-1)[1], "light");
await context.api.setTheme("dark"); media.matches = false; change(); assert.equal(root.dataset.theme, "dark");
await context.api.setTheme("system"); assert.equal(root.dataset.theme, "light");
assert.equal(native.at(-1), "system"); assert.equal(root.style.colorScheme, "light");
let resolve;
context.storeGet = () => new Promise(done => { resolve = done; });
const pending = context.api.initTheme(); await context.api.setTheme("dark"); resolve("light"); await pending;
assert.equal(root.dataset.theme, "dark", "late startup preference cannot replace a new user choice");
console.log("Theme: system changes, forced overrides, persistence, native appearance and startup race passed");
