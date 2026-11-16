// C27.4B: one result per manual timing session.
export function createManualTimingNotificationSession({
  trackId, title, key, initialLrc = null
}) {
  const normalize = value =>
    value == null ? null : String(value);

  const initial = normalize(initialLrc);
  let requested = initial;
  let confirmed = initial;
  let changed = false;
  let finished = false;

  return {
    trackId, title, key,

    request(value) {
      requested = normalize(value);
      changed = true;
    },

    confirm(value) {
      confirmed = normalize(value);
    },

    finish() {
      if (finished) return "already-finalized";
      finished = true;

      if (!changed || requested === initial) {
        return "unchanged";
      }

      return confirmed === requested ? "saved" : "failed";
    },
  };
}
