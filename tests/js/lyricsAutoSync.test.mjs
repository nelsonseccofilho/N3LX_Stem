import assert from "node:assert/strict";
import { createLyricsAutoSyncController } from "../../static/js/lyricsAutoSync.js";

const microtask = () => Promise.resolve();

// The user starts automatic synchronization; no manual timing UI is involved.
{
  const states = [];
  let reads = 0;
  let saved = false;
  const controller = createLyricsAutoSyncController({
    startRequest: async (run) => { assert.equal(run.trackId, "track-1"); return { ok: true, status: 202 }; },
    readStatus: async () => ++reads === 1
      ? { state: "running", progress: 0.35 }
      : { state: "done", matched: 0.92, lines_matched: 33, lines: 36, aligned: { synced: "test" } },
    commit: async () => { saved = true; },
    notify: (run) => states.push(run?.state || "closed"),
    sleep: microtask, maxPolls: 5,
  });
  assert.equal(await controller.start({ trackId: "track-1", entry: { plain: "corrected lyrics" } }), true);
  assert.equal(saved, true);
  assert.deepEqual(states, ["running", "running", "done"]);
  assert.equal(controller.current().linesMatched, 33);
  assert.equal(controller.current().lines, 36);
  controller.dismiss();
  assert.equal(controller.current(), null);
}

// Unsure must never apply guessed timings.
{
  let commits = 0;
  const controller = createLyricsAutoSyncController({
    startRequest: async () => ({ ok: true }),
    readStatus: async () => ({ state: "unsure" }),
    commit: async () => { commits++; },
    notify: () => {},
    sleep: microtask,
  });
  assert.equal(await controller.start({ trackId: "track-2" }), false);
  assert.equal(controller.current().state, "unsure");
  assert.equal(commits, 0);
}

// Protect a newer manual edit instead of overwriting it with stale alignment.
{
  const controller = createLyricsAutoSyncController({
    startRequest: async () => ({ ok: true }),
    readStatus: async () => ({ state: "done", aligned: { synced: "old" } }),
    commit: async () => { const error = Error("edited concurrently"); error.code = "LYRICS_CHANGED"; throw error; },
    notify: () => {},
    sleep: microtask,
  });
  assert.equal(await controller.start({ trackId: "track-3" }), false);
  assert.equal(controller.current().state, "changed");
}

// Reject a second run while one is active; server time remains authoritative.
{
  let resume;
  const controller = createLyricsAutoSyncController({
    startRequest: async () => ({ ok: true }),
    readStatus: async () => ({ state: "unsure" }),
    commit: async () => { throw Error("must not be called"); },
    notify: () => {},
    sleep: () => new Promise((resolve) => { resume = resolve; }),
  });
  const first = controller.start({ trackId: "track-4" });
  await microtask();
  assert.equal(await controller.start({ trackId: "track-5" }), false);
  resume();
  await first;
  assert.equal(controller.current().state, "unsure");
}

console.log("lyricsAutoSync controller: PASS");
