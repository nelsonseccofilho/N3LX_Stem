import test from "node:test";
import assert from "node:assert/strict";
import { karaokeCompletionOutcome as outcome } from
  "../../static/js/karaokeNotificationPolicy.js";

test("only a verified result is complete", () => {
  assert.equal(outcome({
    state: "done",
    available: true,
    current_alignment: { pt: true, en: false }
  }, "pt"), "completed");

  assert.equal(outcome({
    state: "done",
    available: true,
    current_alignment: { pt: true, en: false }
  }, "en"), "failed");
});

test("an old sidecar is not a completed generation", () => {
  assert.equal(
    outcome({ state: "idle", available: true }, "pt"),
    "previous"
  );
});

test("cancellation does not report success", () => {
  assert.equal(
    outcome({ state: "idle", available: true }, "pt", true),
    "cancelled"
  );
});

test("failure and running states remain distinct", () => {
  assert.equal(outcome({ state: "running" }, "en"), "running");
  assert.equal(outcome({ state: "failed" }, "en"), "failed");
  assert.equal(
    outcome({ state: "done", available: false }, "en"),
    "failed"
  );
});
