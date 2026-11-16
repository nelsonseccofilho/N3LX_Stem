import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const main = fs.readFileSync(new URL("../../static/js/main.js", import.meta.url), "utf8");
const code = main.slice(main.indexOf("function wireAutoSectionsToggle()"), main.indexOf("function handleStemChoiceClick"));
let resolveStartup;
let stored = true;
const writes = [];
const btn = {
  attributes: { "aria-pressed": "true" }, disabled: false,
  setAttribute(k, v) { this.attributes[k] = v; },
  getAttribute(k) { return this.attributes[k]; },
  addEventListener(k, fn) { this[k] = fn; },
};
const context = vm.createContext({ console, document: { getElementById: () => btn },
  fetch: async (url, opts) => {
    if (opts?.method === "POST") {
      stored = JSON.parse(opts.body).auto_sections; writes.push(stored);
      return { ok: true, json: async () => ({ auto_sections: stored }) };
    }
    return new Promise((resolve) => { resolveStartup = (on) => resolve({ ok: true, json: async () => ({ auto_sections: on }) }); });
  },
});
vm.runInContext(code, context);
context.wireAutoSectionsToggle();
await btn.click();
assert.equal(stored, false);
resolveStartup(true);
await new Promise(resolve => setImmediate(resolve));
assert.equal(btn.getAttribute("aria-pressed"), "false", "a late startup read cannot undo a user's click");
assert.deepEqual(writes, [false], "startup must not force a preference reset");
context.wireAutoSectionsToggle();
resolveStartup(false);
await new Promise(resolve => setImmediate(resolve));
assert.equal(btn.getAttribute("aria-pressed"), "false", "saved opt-out survives reopening");
await btn.click();
assert.equal(stored, true);
assert.equal(btn.getAttribute("aria-pressed"), "true");
assert.ok(!fs.readFileSync(new URL("../../static/js/player.js", import.meta.url), "utf8").includes("autoSectionsResetFn"), "opening a song must not reset import settings");
console.log("Structure preference: persisted choice, startup race and song-change preservation passed.");
