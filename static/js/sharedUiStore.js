// Only app preferences are shared; browser profiles, cookies and credentials stay untouched.
const keys = new Set(["stemdeck.folders", "stemdeck.deleted_jobs", "stemdeck.language", "stemdeck:selected-stems", "stemdeck:vocal-split-mode", "stemdeck:failures", "stemdeck:beatgrid-prefs", "stemdeck:slow-speed", "stemdeck:metronome", "stemdeck:setlist"]);
const allowed = (key) => keys.has(key) || /^stemdeck:(mix|lyrics):[a-zA-Z0-9_-]{1,80}$/.test(key);
let loading;
let values;

async function load() {
  if (loading) return loading;
  loading = (async () => {
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
      return values;
    } catch (error) { console.warn("[preferences] local fallback", error); return null; }
  })();
  return loading;
}

export async function sharedGet(key) {
  if (!allowed(key)) return undefined;
  const store = await load();
  return store && Object.hasOwn(store, key) ? structuredClone(store[key]) : undefined;
}
export async function sharedSet(key, value) {
  if (!allowed(key) || !(await load())) return;
  values[key] = structuredClone(value);
  const response = await fetch("/api/ui-store", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({values:{[key]:value}}) });
  if (!response.ok) throw new Error("Could not save local preferences");
}
