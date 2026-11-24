"use strict";

// Only synthetic dates and inputs: none of these tests reads the local store.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { currentTimeChoice, resolvePresentTime, defaultPresentIndex, draftFingerprint,
  splitInterval, mergeIntervals, validateRefreshSnapshot } = require("../static/manual.js");

const DATE = "2026-11-22", ZONE = "America/Los_Angeles";
const NOW = Date.parse("2026-11-23T06:30:00Z"); // 22:30 local
const MIDNIGHT = Date.parse("2026-11-23T08:00:00Z");

test("only the final interval of the local current day defaults to present", () => {
  for (const count of [1, 2, 4, 12]) {
    assert.equal(defaultPresentIndex(DATE, DATE, ZONE, count, null, false, NOW), count - 1);
    for (let i = 0; i < count; i++) {
      assert.equal(currentTimeChoice(DATE, DATE, ZONE, i, count, false, NOW), i === count - 1 ? "22:30" : null);
    }
  }
  assert.equal(defaultPresentIndex(DATE, DATE, ZONE, 0, null, false, NOW), -1);
  assert.equal(defaultPresentIndex("2026-11-21", DATE, ZONE, 4, null, false, NOW), -1);
  assert.equal(currentTimeChoice(DATE, DATE, ZONE, 3, 4, true, NOW), null);
});

test("automatic live tail is not converted into an editable manual present interval", () => {
  const active = { locked_from: "2026-11-22T20:00:00-08:00", save_blocked: false };
  assert.equal(defaultPresentIndex(DATE, DATE, ZONE, 4, active, false, NOW), -1);
  // Unavailable status does not imply a connection, but must not invent a
  // fixed end for a manually edited current-day last interval either.
  assert.equal(defaultPresentIndex(DATE, DATE, ZONE, 4, null, true, NOW), 3);
});

test("date rollover and invalid timezone never retain a stale present selection", () => {
  assert.equal(defaultPresentIndex(DATE, DATE, ZONE, 1, null, false, MIDNIGHT), -1);
  assert.equal(defaultPresentIndex(DATE, DATE, "invalid/timezone", 1, null, false, NOW), -1);
  assert.throws(() => resolvePresentTime(DATE, DATE, ZONE, 0, 1, false, "22:00", MIDNIGHT));
  assert.throws(() => resolvePresentTime(DATE, DATE, ZONE, 0, 1, false, "22:30", NOW));
});

test("time passing alone never marks a viewed record as edited", () => {
  const before = { date: DATE, kind: "intervals_override", note: "",
    intervals: [{start: "09:00", end: "10:00"}, {start: "20:00", end: "22:30"}] };
  const later = { ...before, intervals: [before.intervals[0], {start: "20:00", end: "22:31"}] };
  assert.equal(draftFingerprint(before, true), draftFingerprint(later, true));
  assert.notEqual(draftFingerprint(before, false), draftFingerprint(later, false));
  assert.notEqual(draftFingerprint(before, true), draftFingerprint({...later, note: "changed"}, true));
  assert.notEqual(draftFingerprint(before, true), draftFingerprint({...later, intervals: [{start:"09:00", end:"10:01"}, later.intervals[1]]}, true));
});

test("after adding, deleting, splitting and merging, the present target is still the last interval", () => {
  const initial = [{start:"09:00", end:"11:00"}, {start:"13:00", end:"14:00"}];
  const added = [...initial, {start:"15:00", end:"16:00"}];
  const split = splitInterval(added, 2);
  const merged = mergeIntervals(split, 2).intervals;
  for (const spans of [initial, added, split, merged, merged.slice(0, -1)]) {
    assert.equal(defaultPresentIndex(DATE, DATE, ZONE, spans.length, null, false, NOW), spans.length - 1);
  }
  assert.equal(defaultPresentIndex(DATE, DATE, ZONE, 0, null, false, NOW), -1);
});

test("updating a cutoff cannot cross an active lock or a concurrent revision", () => {
  const revision = "a".repeat(64), start = Date.parse("2026-11-23T05:00:00Z") / 1000;
  const old = {edit_revision: revision, edit_cutoff: start};
  const latest = {date: DATE, timezone: ZONE, edit_revision: revision, edit_cutoff: start + 60,
    today_override_available: true, editable_intervals: [],
    active_tracking: {locked_from: new Date((start + 60) * 1000).toISOString(), save_blocked: false}};
  assert.equal(validateRefreshSnapshot(old, latest, DATE, ZONE), latest.active_tracking);
  assert.throws(() => validateRefreshSnapshot(old, {...latest, active_tracking: {...latest.active_tracking, locked_from: new Date(start * 1000).toISOString()}}, DATE, ZONE));
  assert.throws(() => validateRefreshSnapshot(old, {...latest, active_tracking: {...latest.active_tracking, save_blocked:true}}, DATE, ZONE));
  assert.throws(() => validateRefreshSnapshot(old, {...latest, edit_revision: "b".repeat(64)}, DATE, ZONE));
});
