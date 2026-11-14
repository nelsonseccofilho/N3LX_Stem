// Automatic line alignment is independent from the manual T/Enter editor.
// No audio is imported, separated or altered here; the backend uses existing vocals.
// Keep polling even if the user switches tracks in the same tab.
export function createLyricsAutoSyncController({
  startRequest, readStatus, commit, notify, sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  pollMs = 1000, maxPolls = 1800,
}) {
  let current = null;

  function publish(run) {
    notify(run ? { ...run } : null);
  }

  return {
    current: () => current,
    dismiss() {
      if (current && current.state !== "running") {
        current = null;
        publish(null);
      }
    },
    async start(input) {
      if (current?.state === "running") return false;
      const run = {
        ...input, state: "running", progress: null,
        matched: null, linesMatched: null, lines: null, error: null,
      };
      current = run;
      publish(run);
      let idle = 0;
      let networkErrors = 0;
      try {
        const response = await startRequest(run);
        if (!response?.ok) throw new Error(`POST /lyrics/retime: HTTP ${response?.status || "unknown"}`);
        for (let attempt = 0; attempt < maxPolls; attempt++) {
          await sleep(pollMs);
          if (current !== run) return false;
          let status;
          try {
            status = await readStatus(run);
            networkErrors = 0;
          } catch (error) {
            if (++networkErrors > 3) throw error;
            continue;
          }
          if (status?.state === "running") {
            const value = Number(status.progress);
            run.progress = Number.isFinite(value) && value > 0 && value <= 1 ? value : null;
            publish(run);
            continue;
          }
          if (status?.state === "idle" && ++idle <= 3) continue;
          if (status?.state === "done") {
            await commit(run, status);
            run.state = "done";
            run.matched = Number.isFinite(status.matched) ? status.matched : null;
            run.linesMatched = Number.isInteger(status.lines_matched) ? status.lines_matched : null;
            run.lines = Number.isInteger(status.lines) ? status.lines : null;
          } else {
            run.state = status?.state === "unsure" ? "unsure" : "failed";
          }
          run.progress = null;
          publish(run);
          return run.state === "done";
        }
        run.state = "timeout";
      } catch (error) {
        run.state = error?.code === "LYRICS_CHANGED" ? "changed" : "failed";
        run.error = String(error?.message || error);
      }
      run.progress = null;
      publish(run);
      return false;
    },
  };
}
