"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { hasOverlappingIntervals } = require("../static/manual.js");

test("warn only when work intervals overlap, not when they touch", () => {
  assert.equal(hasOverlappingIntervals([]), false);
  assert.equal(hasOverlappingIntervals([{start:"09:00",end:"12:00"},{start:"12:00",end:"15:00"}]), false);
  assert.equal(hasOverlappingIntervals([{start:"12:00",end:"15:00"},{start:"09:00",end:"13:00"}]), true);
  assert.equal(hasOverlappingIntervals([{start:"09:00",end:"17:00"},{start:"10:00",end:"11:00"}]), true);
  assert.throws(() => hasOverlappingIntervals([{start:"10:00",end:"09:00"}]));
});
