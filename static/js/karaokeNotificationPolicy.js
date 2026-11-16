// A completed run must have a verified sidecar for its language.
export function karaokeCompletionOutcome(
  status, language, cancelled = false
) {
  if (cancelled) return "cancelled";
  if (status?.state === "running") return "running";
  if (status?.state === "failed") return "failed";
  if (status?.state === "done") {
    return status.available === true &&
      status.current_alignment?.[language] === true
      ? "completed" : "failed";
  }
  if (status?.state === "idle") {
    return status.available ? "previous" : "cancelled";
  }
  return "failed";
}
