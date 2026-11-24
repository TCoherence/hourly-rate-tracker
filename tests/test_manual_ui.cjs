"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { validDate, monthDays, normalizeIntervals, buildEntry, initialEditorKind, shouldPrefillIntervals, splitInterval, mergeIntervals, currentTimeChoice, rebaseIntervals, validateRefreshSnapshot } = require("../static/manual.js");

test("current time is a one-time choice only on today's last visible interval", () => {
  const now = Date.parse("2026-11-23T06:30:45Z"); // 22:30 in Los Angeles on November 22
  assert.equal(currentTimeChoice("2026-11-22", "2026-11-22", "America/Los_Angeles", 3, 4, false, now), "22:30");
  assert.equal(currentTimeChoice("2026-11-22", "2026-11-22", "America/Los_Angeles", 2, 4, false, now), null);
  assert.equal(currentTimeChoice("2026-11-21", "2026-11-22", "America/Los_Angeles", 3, 4, false, now), null);
  assert.equal(currentTimeChoice("2026-11-22", "2026-11-22", "America/Los_Angeles", 3, 4, true, now), null);
  assert.equal(currentTimeChoice("2026-11-22", "2026-11-22", "America/Los_Angeles", 3, 4, false, Date.parse("2026-11-23T08:00:00Z")), null);
  assert.equal(currentTimeChoice("2026-11-22", "2026-11-22", "invalid/timezone", 3, 4, false, now), null);
  assert.throws(() => buildEntry({ date: "2026-11-22", kind: "intervals", intervals: [{start:"22:31", end:"22:30"}] }, "2026-11-22"));
});

test("refreshing a correction preserves the draft and adds only work in the new range", () => {
  const draft = [{start:"09:00",end:"10:00"}, {start:"10:45",end:"11:30"}];
  const observed = [{start:"09:00",end:"10:20"}, {start:"10:50",end:"11:10"}, {start:"12:00",end:"13:00"}];
  const result = rebaseIntervals(draft, observed, "10:00", "11:00");
  assert.deepEqual(result.intervals, [{start:"09:00",end:"10:00"}, {start:"10:00",end:"10:20"}, {start:"10:45",end:"11:30"}]);
  assert.equal(result.added, 20);
  assert.deepEqual(draft, [{start:"09:00",end:"10:00"}, {start:"10:45",end:"11:30"}]);
  assert.deepEqual(observed[0], {start:"09:00",end:"10:20"});
});

test("refresh refuses a stale boundary, invalid observations or too many resulting segments", () => {
  assert.throws(() => rebaseIntervals([], [], "10:00", "10:00"));
  assert.throws(() => rebaseIntervals([], [], "10:00", "09:59"));
  assert.throws(() => rebaseIntervals([], [{start:"10:00",end:"09:00"}], "10:00", "11:00"));
  const draft = Array.from({length:12}, (_, n) => ({start:`00:${String(n*2).padStart(2,"0")}`,end:`00:${String(n*2+1).padStart(2,"0")}`}));
  assert.throws(() => rebaseIntervals(draft, [{start:"10:01",end:"10:02"}], "10:00", "11:00"), /12/);
  assert.equal(draft.length, 12);
});

test("newly observed work does not erase a user's adjacent split", () => {
  const draft = [{start:"09:00",end:"10:15"}, {start:"10:15",end:"10:30"}];
  const result = rebaseIntervals(draft, [{start:"10:00",end:"11:00"}], "10:00", "11:00");
  assert.deepEqual(result.intervals, [{start:"09:00",end:"10:15"}, {start:"10:15",end:"11:00"}]);
  assert.equal(result.added, 30);
});

test("new correction snapshots require the same date, timezone and revision and respect the live lock", () => {
  const date = "2026-11-22", zone = "America/Los_Angeles", revision = "a".repeat(64);
  const cutoff = Date.parse("2026-11-23T06:00:00Z") / 1000;
  const old = { edit_cutoff: cutoff, edit_revision: revision };
  const next = { date, timezone: zone, edit_cutoff: cutoff + 60, edit_revision: revision, today_override_available: true, editable_intervals: [], active_tracking: null };
  assert.equal(validateRefreshSnapshot(old, next, date, zone), null);
  for (const bad of [
    {date:"2026-11-21"}, {timezone:"UTC"}, {edit_revision:"b".repeat(64)},
    {edit_cutoff:cutoff-60}, {today_override_available:false}, {editable_intervals:null},
    {active_tracking:{locked_from:"invalid"}}, {active_tracking:{locked_from:new Date(cutoff*1000).toISOString()}},
    {active_tracking:{locked_from:new Date((cutoff+60)*1000).toISOString(),save_blocked:true}},
  ]) assert.throws(() => validateRefreshSnapshot(old, {...next, ...bad}, date, zone));
  const active = {locked_from:new Date((cutoff+60)*1000).toISOString(),save_blocked:false};
  assert.equal(validateRefreshSnapshot(old, {...next, active_tracking:active}, date, zone), active);
});

test("calendar rejects overflow dates and follows leap-year dates", () => {
  assert.equal(validDate("2024-02-29"), true);
  for (const day of ["2037-02-29", "2037-11-31", "2037-1-01", "0000-01-01", "invalid"]) assert.equal(validDate(day), false);
  assert.equal(monthDays("2024-02").filter(Boolean).length, 29);
  assert.equal(monthDays("2037-02").filter(Boolean).length, 28);
});

test("calendar begins on Monday and retains all days in a 42-cell grid", () => {
  const days = monthDays("2037-11");
  assert.equal(days.length, 42);
  assert.deepEqual(days.slice(0, 6), Array(6).fill(null));
  assert.equal(days[6], "2037-11-01");
  assert.equal(days.filter(Boolean).at(-1), "2037-11-30");
  assert.equal(monthDays("0001-01")[0], "0001-01-01");
});

test("24-hour entries allow more than twelve hours and end at midnight", () => {
  const result = normalizeIntervals([{ start: "09:00", end: "24:00" }]);
  assert.equal(result.minutes, 15 * 60);
  assert.deepEqual(result.intervals, [{ start: "09:00", end: "24:00" }]);
});

test("overlapping ranges merge, touching ranges keep their boundary", () => {
  const values = [{ start: "19:00", end: "21:00" }, { start: "09:00", end: "16:00" }, { start: "15:00", end: "19:00" }];
  const original = JSON.stringify(values), result = normalizeIntervals(values);
  assert.equal(result.minutes, 12 * 60);
  assert.deepEqual(result.intervals, [{ start: "09:00", end: "19:00" }, { start: "19:00", end: "21:00" }]);
  assert.equal(JSON.stringify(values), original);
});

test("splitting retains the exact total and the boundary in the saved entry", () => {
  const values = [{start:"09:00",end:"24:00"}], split = splitInterval(values, 0);
  assert.deepEqual(split, [{start:"09:00",end:"16:30"},{start:"16:30",end:"24:00"}]);
  assert.deepEqual(buildEntry({date:"2037-11-11",kind:"intervals_override",intervals:split}, "2037-11-12").intervals, split);
  assert.equal(normalizeIntervals(split).minutes, 900);
  assert.deepEqual(values, [{start:"09:00",end:"24:00"}]);
  assert.throws(() => splitInterval([{start:"09:00",end:"09:01"}], 0));
  assert.throws(() => splitInterval(Array(12).fill({start:"09:00",end:"10:00"}), 0));
});

test("merging adjacent intervals reports any newly counted gap accurately", () => {
  const touching = [{start:"09:00",end:"12:00"},{start:"12:00",end:"17:00"}];
  assert.deepEqual(mergeIntervals(touching, 0), {intervals:[{start:"09:00",end:"17:00"}],gap:0,added:0});
  const separated = [{start:"09:00",end:"12:00"},{start:"13:00",end:"17:00"}];
  assert.deepEqual(mergeIntervals(separated, 0), {intervals:[{start:"09:00",end:"17:00"}],gap:60,added:60});
  const withCover = [...separated, {start:"12:30",end:"13:00"}];
  assert.equal(mergeIntervals(withCover, 0).added, 30);
  assert.throws(() => mergeIntervals(separated, 1));
});

test("invalid, overnight and zero-length time ranges are rejected", () => {
  for (const pair of [["24:00", "24:00"], ["23:00", "01:00"], ["09:00", "09:00"], ["09:00", "24:01"], ["09:60", "10:00"], ["-1:00", "10:00"]]) {
    assert.throws(() => normalizeIntervals([{ start: pair[0], end: pair[1] }]));
  }
  assert.throws(() => normalizeIntervals([]));
  assert.throws(() => normalizeIntervals(Array(13).fill({ start: "09:00", end: "10:00" })));
});

test("past-day totals include explicit zero, while today and future totals are rejected", () => {
  const draft = { date: "2037-11-11", kind: "daily_total", hours: "0", note: "  休息  " };
  assert.deepEqual(buildEntry(draft, "2037-11-12"), { date: draft.date, kind: draft.kind, hours: 0, note: "休息" });
  for (const hours of ["", " ", "NaN", "Infinity", "-1", "24.01"]) assert.throws(() => buildEntry({ ...draft, hours }, "2037-11-12"));
  assert.throws(() => buildEntry({ ...draft, date: "2037-11-12" }, "2037-11-12"));
  assert.throws(() => buildEntry({ ...draft, date: "2037-11-13" }, "2037-11-12"));
});

test("today's structured intervals produce the unchanged API shape", () => {
  const result = buildEntry({ date: "2037-11-12", kind: "intervals", note: "午后补录", intervals: [{ start: "08:00", end: "15:00" }, { start: "18:00", end: "20:00" }] }, "2037-11-12");
  assert.deepEqual(result, { date: "2037-11-12", kind: "intervals", note: "午后补录", intervals: [{ start: "08:00", end: "15:00" }, { start: "18:00", end: "20:00" }] });
  assert.throws(() => buildEntry({ ...result, date: "2037-11-13" }, "2037-11-12"));
  assert.throws(() => buildEntry({ ...result, note: "a".repeat(501) }, "2037-11-12"));
});

test("today's correction retains the server snapshot and permits removing all work", () => {
  const draft = { date: "2037-11-12", kind: "intervals_override", note: "", intervals: [{ start: "09:00", end: "17:00" }] };
  assert.deepEqual(buildEntry(draft, "2037-11-13"), draft);
  assert.throws(() => buildEntry(draft, "2037-11-12"));
  const revision = "a".repeat(64), cutoff = 1794531720;
  assert.deepEqual(buildEntry(draft, "2037-11-12", cutoff, revision), { ...draft, edit_cutoff: cutoff, edit_revision: revision });
  assert.deepEqual(buildEntry({ ...draft, intervals: [] }, "2037-11-12", cutoff, revision).intervals, []);
  assert.throws(() => buildEntry(draft, "2037-11-12", cutoff, "bad"));
  assert.throws(() => buildEntry({ ...draft, date: "2037-11-13" }, "2037-11-12", cutoff, revision));
});

test("today and past dates default to correction while total estimates remain safe", () => {
  const today = "2037-11-13", past = "2037-11-12";
  assert.equal(initialEditorKind(null, past, today), "intervals_override");
  assert.equal(initialEditorKind({kind:"intervals"}, past, today), "intervals_override");
  assert.equal(initialEditorKind({kind:"intervals_override"}, past, today), "intervals_override");
  assert.equal(initialEditorKind({kind:"daily_total"}, past, today), "daily_total");
  assert.equal(initialEditorKind(null, today, today), "intervals_override");
  assert.equal(initialEditorKind({kind:"intervals"}, today, today), "intervals_override");
  assert.equal(shouldPrefillIntervals(null, past, today), true);
  assert.equal(shouldPrefillIntervals({kind:"intervals"}, past, today), true);
  assert.equal(shouldPrefillIntervals({kind:"intervals_override"}, past, today), false);
  assert.equal(shouldPrefillIntervals({kind:"daily_total"}, past, today), false);
  assert.equal(shouldPrefillIntervals(null, today, today), true);
  assert.equal(shouldPrefillIntervals({kind:"intervals_override",edit_cutoff:123}, past, today), true);
  assert.equal(shouldPrefillIntervals({kind:"intervals_override",edit_cutoff:123}, today, today), true);
});

test('timeline boundaries remain within the day and cannot cross', () => {
  const { adjustBoundary } = require('../static/manual.js');
  assert.deepEqual(adjustBoundary(540, 1020, 'start', 1140), [1019, 1020]);
  assert.deepEqual(adjustBoundary(540, 1020, 'end', 120), [540, 541]);
  assert.deepEqual(adjustBoundary(540, 1020, 'end', 1500), [540, 1440]);
  assert.deepEqual(adjustBoundary(540, 0, 'start', 0), [0, 1]);
});
