const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createDraftUndo } = require("../static/draft-undo.js");

function draft(date, intervals, present = false) { return { date, kind: "intervals_override", intervals, present }; }
function span(start, end) { return { start, end }; }

test("undo retains the original draft through split, merge, delete and add", () => {
  const undo = createDraftUndo();
  const original = draft("2026-11-22", [span("09:00", "12:00")]);
  const split = draft(original.date, [span("09:00", "10:30"), span("10:30", "12:00")]);
  const removed = draft(original.date, [span("09:00", "10:30")]);
  assert.equal(undo.record(original, split), true);
  assert.equal(undo.record(split, removed), true);
  assert.deepEqual(undo.peek(original.date), split);
  assert.equal(undo.discard(original.date), true);
  assert.deepEqual(undo.peek(original.date), original);
  assert.equal(undo.discard(original.date), true);
  assert.equal(undo.peek(original.date), null);
});

test("a continuous drag is one step and a second gesture is independent", () => {
  const undo = createDraftUndo();
  const a = draft("2026-11-22", [span("09:00", "12:00")]);
  const b = draft(a.date, [span("09:01", "12:00")]);
  const c = draft(a.date, [span("09:02", "12:00")]);
  undo.record(a, b, "drag"); undo.record(b, c, "drag");
  assert.equal(undo.size(), 1); assert.deepEqual(undo.peek(a.date), a);
  undo.endGroup(); undo.record(c, b, "drag");
  assert.equal(undo.size(), 2); assert.deepEqual(undo.peek(a.date), c);
});

test("clock-driven present changes are not undo steps", () => {
  const undo = createDraftUndo();
  const a = draft("2026-11-22", [span("09:00", "10:00")], true);
  const b = draft(a.date, [span("09:00", "10:01")], true);
  assert.equal(undo.record(a, b), false); assert.equal(undo.size(), 0);
  const c = draft(a.date, [span("09:30", "10:02")], true);
  assert.equal(undo.record(b, c), true); assert.deepEqual(undo.peek(a.date), b);
});

test("date guard, snapshots, reset and bounded memory protect drafts", () => {
  const undo = createDraftUndo(1);
  const a = draft("2026-11-22", [span("09:00", "12:00")]);
  const b = draft(a.date, [span("09:01", "12:00")]);
  const c = draft(a.date, [span("09:02", "12:00")]);
  assert.equal(undo.record(a, {...b, date:"2026-11-23"}), false);
  undo.record(a, b); undo.record(b, c); b.intervals[0].start = "08:00";
  assert.equal(undo.size(), 1); assert.equal(undo.peek("2026-11-23"), null);
  assert.equal(undo.discard("2026-11-23"), false);
  const peeked = undo.peek(a.date); assert.equal(peeked.intervals[0].start, "09:01");
  peeked.intervals[0].start = "00:00";
  assert.equal(undo.peek(a.date).intervals[0].start, "09:01");
  undo.reset(); assert.equal(undo.size(), 0);
});
