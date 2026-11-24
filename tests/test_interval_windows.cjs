"use strict";

const {test} = require("node:test");
const assert = require("node:assert/strict");
const {intervalWindow, adjustIntervalBoundary, intervalsInOrder, insertionForGap, rebaseIntervals} = require("../static/manual.js");

test("each segment uses the window between its neighbours and today limit", () => {
  const spans = [{start:"09:00",end:"12:00"},{start:"13:00",end:"15:00"},{start:"16:00",end:"18:00"}];
  assert.deepEqual(intervalWindow(spans, 0, 1200), {min:0,max:780,conflict:false});
  assert.deepEqual(intervalWindow(spans, 1, 1200), {min:720,max:960,conflict:false});
  assert.deepEqual(intervalWindow(spans, 2, 1200), {min:900,max:1200,conflict:false});
});

test("moving either handle respects neighbours, a minute minimum and touching boundaries", () => {
  const spans = [{start:"09:00",end:"12:00"},{start:"13:00",end:"15:00"},{start:"16:00",end:"18:00"}];
  assert.deepEqual(adjustIntervalBoundary(spans, 1, "start", 100, 1200), [720,900]);
  assert.deepEqual(adjustIntervalBoundary(spans, 1, "start", 999, 1200), [899,900]);
  assert.deepEqual(adjustIntervalBoundary(spans, 1, "end", 500, 1200), [780,781]);
  assert.deepEqual(adjustIntervalBoundary(spans, 1, "end", 1000, 1200), [780,960]);
  assert.deepEqual(adjustIntervalBoundary(spans, 2, "end", 1440, 1100), [960,1100]);
  assert.deepEqual(spans[1], {start:"13:00",end:"15:00"});
});

test("old overlapping or out-of-order drafts remain editable but cannot be saved as ordered", () => {
  const draft = [{start:"09:00",end:"12:00"},{start:"11:00",end:"13:00"}];
  assert.equal(intervalsInOrder(draft,true), false);
  assert.deepEqual(intervalWindow(draft,0,1440), {min:0,max:1440,conflict:true});
  assert.deepEqual(adjustIntervalBoundary(draft,0,"end",660,1440), [540,660]);
  const repaired = [{start:"09:00",end:"11:00"},{start:"11:00",end:"13:00"}];
  assert.equal(intervalsInOrder(repaired,true), true);
  assert.equal(intervalsInOrder([{start:"14:00",end:"15:00"},{start:"09:00",end:"10:00"}],true), false);
  assert.throws(() => rebaseIntervals(draft,[],"10:00","11:00"), /草稿未改变/);
  assert.deepEqual(draft[0], {start:"09:00",end:"12:00"});
});

test("adding a segment selects a free chronological gap and never changes existing rows", () => {
  const spans = [{start:"09:00",end:"12:00"},{start:"13:00",end:"17:00"}];
  assert.deepEqual(insertionForGap(spans, 1020), {index:1,interval:{start:"12:00",end:"13:00"}});
  assert.deepEqual(insertionForGap(spans, 1440), {index:2,interval:{start:"17:00",end:"18:00"}});
  assert.deepEqual(insertionForGap([], 1440), {index:0,interval:{start:"09:00",end:"10:00"}});
  assert.throws(() => insertionForGap([{start:"00:00",end:"10:00"}],600), /没有空闲/);
  assert.throws(() => insertionForGap([{start:"08:00",end:"10:00"},{start:"09:00",end:"11:00"}],720), /重叠/);
  assert.deepEqual(spans[1], {start:"13:00",end:"17:00"});
});
