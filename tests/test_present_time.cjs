"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { resolvePresentTime, buildEntry } = require("../static/manual.js");

test("present resolves at the current minute, not when the option was selected", () => {
  const date = "2026-11-22", zone = "America/Los_Angeles";
  const first = Date.parse("2026-11-23T06:30:10Z");
  const later = Date.parse("2026-11-23T06:32:59Z");
  assert.equal(resolvePresentTime(date, date, zone, 1, 2, false, "22:00", first), "22:30");
  assert.equal(resolvePresentTime(date, date, zone, 1, 2, false, "22:00", later), "22:32");
  const saved = buildEntry({ date, kind: "intervals", intervals: [{ start: "22:00", end: "22:32" }] }, date);
  assert.deepEqual(saved.intervals, [{ start: "22:00", end: "22:32" }]);
  assert.equal(JSON.stringify(saved).includes("present"), false);
});

test("present cannot point to a future start, prior day or hidden time", () => {
  const date = "2026-11-22", zone = "America/Los_Angeles", now = Date.parse("2026-11-23T06:30:00Z");
  assert.throws(() => resolvePresentTime(date, date, zone, 0, 1, false, "22:30", now), /晚于/);
  assert.throws(() => resolvePresentTime(date, date, zone, 0, 1, false, "22:31", now), /晚于/);
  assert.throws(() => resolvePresentTime(date, date, zone, 0, 1, false, "22:00", Date.parse("2026-11-23T08:00:00Z")), /日期已变化/);
  assert.throws(() => resolvePresentTime(date, date, zone, 0, 1, true, "22:00", now));
  assert.throws(() => resolvePresentTime(date, date, zone, 0, 2, false, "22:00", now));
});
