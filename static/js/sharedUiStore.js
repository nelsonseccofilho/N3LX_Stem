// Only app preferences are shared; browser profiles, cookies and credentials stay untouched.
const keys = new Set(["stemdeck.folders", "stemdeck.deleted_jobs", "stemdeck.language", "stemdeck:selected-stems", "stemdeck:vocal-split-mode", "stemdeck:failures", "stemdeck:beatgrid-prefs", "stemdeck:slow-speed", "stemdeck:metronome", "stemdeck:setlist"]);
const allowed = (key) => keys.has(key) || /^stemdeck:(mix|lyrics):[a-zA-Z0-9_-]{1,80}$/.test(key);
let loading;
let values;

// Keep failed/unacknowledged writes across reloads. A temporary startup
// timeout must never make an older server snapshot replace local edits.
const pendingKey = "stemdeck.pending-ui-writes.v1";
let writeChain = Promise.resolve();
const latestTokens = new Map();
function pendingWrites() {
  try { return JSON.parse(localStorage.getItem(pendingKey) || "{}"); }
  catch { return {}; }
}
function putPending(pending) { localStorage.setItem(pendingKey, JSON.stringify(pending)); }
function send(key, entry) {
  const task = writeChain.catch(() => {}).then(async () => {
    const latest = latestTokens.get(key) || pendingWrites()[key]?.token;
    if (latest && latest !== entry.token) return;
    latestTokens.set(key, entry.token);
    const response = await fetch("/api/ui-store", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({values:{[key]:entry.value}}), signal:AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error("Could not save local preferences");
    const pending = pendingWrites();
    if (pending[key]?.token === entry.token) { delete pending[key]; putPending(pending); }
  });
  writeChain = task;
  return task;
}

async function load() {
  if (loading) return loading;
  loading = (async () => {
    let completed = false;
    try {
      const response = await fetch("/api/ui-store", { signal: AbortSignal.timeout(5000) });
      if (!response.ok) return null;
      values = (await response.json()).values || {};
      const url = new URL(window.location.href);
      const migration = url.searchParams.get("migrate-ui") === "1";
      if (migration || !Object.keys(values).length) {
        const local = {};
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (allowed(key)) {
            try { local[key] = JSON.parse(localStorage.getItem(key)); } catch {}
          }
        }
        if (Object.keys(local).length) {
          const saved = await fetch("/api/ui-store", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({values:local,migration}) });
          if (!saved.ok) throw new Error("Could not preserve browser preferences");
          values = {...values, ...local};
        }
        if (migration) { url.searchParams.delete("migrate-ui"); history.replaceState(null, "", url); }
      }
      for (const [key, entry] of Object.entries(pendingWrites())) {
        if (!allowed(key) || !entry || !Object.hasOwn(entry, "value")) continue;
        values[key] = structuredClone(entry.value);
        try { await send(key, entry); } catch (error) { console.warn("[preferences] pending write retained", error); }
      }
      completed = true;
      return values;
    } catch (error) { console.warn("[preferences] local fallback", error); return null; }
    finally { if (!completed) loading = null; }
  })();
  return loading;
}

export async function sharedGet(key) {
  if (!allowed(key)) return undefined;
  const store = await load();
  const pending = pendingWrites()[key];
  if (pending && Object.hasOwn(pending, "value")) return structuredClone(pending.value);
  return store && Object.hasOwn(store, key) ? structuredClone(store[key]) : undefined;
}
export async function sharedSet(key, value) {
  if (!allowed(key)) return;
  const entry = { value: structuredClone(value), token: `${Date.now()}-${Math.random()}` };
  latestTokens.set(key, entry.token);
  const pending = pendingWrites(); pending[key] = entry; putPending(pending);
  await load();
  values ||= {};
  if (latestTokens.get(key) === entry.token) values[key] = structuredClone(value);
  // Write even if the initial GET failed; the durable journal is removed only
  // after acknowledgement of this exact version, never an older one.
  await send(key, entry);
}
