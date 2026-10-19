// Playback sequence independent of the renderer, audio engine and persistence.
export function createSetlistPlayer({ open, play, stop, changed = () => {} }) {
  let ids = [], index = -1, status = "idle", error = "", generation = 0, pending = null;
  const busy = () => ["loading", "playing", "paused"].includes(status);
  const state = () => ({ ids: [...ids], index, status, error, currentId: ids[index] || null, busy: busy() });
  const notify = () => changed(state());
  function cancel(stopAudio = true) {
    generation++;
    pending?.abort();
    pending = null;
    status = "idle";
    error = "";
    if (stopAudio) stop();
    notify();
  }
  async function start(at = 0) {
    if (!Number.isInteger(at) || at < 0 || at >= ids.length) return false;
    generation++;
    pending?.abort();
    const token = generation;
    const controller = new AbortController();
    pending = controller;
    stop();
    index = at;
    status = "loading";
    error = "";
    notify();
    try {
      await open(ids[index], controller.signal);
      if (token !== generation) return false;
      if (await play() === false) throw new Error("playback");
      if (token !== generation) return false;
      status = "playing";
      pending = null;
      notify();
      return true;
    } catch (e) {
      if (token !== generation) return false;
      pending = null;
      status = "error";
      error = String(e?.message || e);
      stop();
      notify();
      return false;
    }
  }
  return {
    state, start, cancel,
    setItems(next) {
      if (busy()) return false;
      ids = [...new Set(next.filter(id => typeof id === "string" && /^[a-zA-Z0-9_-]{1,80}$/.test(id)))];
      index = -1; status = "idle"; error = ""; notify(); return true;
    },
    ended(id) {
      if (status !== "playing" || ids[index] !== id) return Promise.resolve(false);
      if (index + 1 < ids.length) return start(index + 1);
      status = "completed"; notify(); return Promise.resolve(true);
    },
    transport(action) {
      if (!busy()) return;
      if (action === "stop" || status === "loading") { cancel(false); return; }
      status = action === "pause" ? "paused" : "playing"; notify();
    },
    fail(message) {
      generation++; pending?.abort(); pending = null;
      status = "error"; error = String(message || "playback"); stop(); notify();
    },
    next() { return index + 1 < ids.length ? start(index + 1) : Promise.resolve(false); },
    previous() { return index > 0 ? start(index - 1) : Promise.resolve(false); },
  };
}
