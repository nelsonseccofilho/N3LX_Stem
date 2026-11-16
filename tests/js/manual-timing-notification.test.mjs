import test from "node:test";
import assert from "node:assert/strict";
import {
  createManualTimingNotificationSession
} from "../../static/js/manualTimingNotification.js";

function session(initialLrc = null) {
  return createManualTimingNotificationSession({
    trackId: "track-test",
    title: "Test song",
    key: "sync:manual:track-test",
    initialLrc,
  });
}

test("close without edits remains silent", () => {
  assert.equal(session().finish(), "unchanged");
});

test("several confirmed edits create one success", () => {
  const run = session("original");
  run.request("first");
  run.confirm("first");
  run.request("second");
  run.confirm("second");
  assert.equal(run.finish(), "saved");
  assert.equal(run.finish(), "already-finalized");
});

test("undo to initial state remains silent", () => {
  const run = session("original");
  run.request("changed");
  run.confirm("changed");
  run.request("original");
  run.confirm("original");
  assert.equal(run.finish(), "unchanged");
});

test("failed final save cannot report success", () => {
  const run = session("original");
  run.request("changed");
  assert.equal(run.finish(), "failed");
});

test("earlier success cannot hide later failure", () => {
  const run = session("original");
  run.request("first");
  run.confirm("first");
  run.request("second");
  assert.equal(run.finish(), "failed");
});

test("removing stored manual timing counts as an edit", () => {
  const run = session("old timing");
  run.request(null);
  run.confirm(null);
  assert.equal(run.finish(), "saved");
});
