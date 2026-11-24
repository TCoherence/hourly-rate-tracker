"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createDraftUndo } = require("../static/draft-undo.js");

test("language changes do not make a moving-present draft dirty or destroy undo", () => {
  let lang = "zh";
  const dictionary = {};
  const context = {
    window: { hourlyI18n: {
      register(values) { Object.assign(dictionary, values); },
      t(key) { return lang === "en" ? dictionary[key] || key : key; },
      language() { return lang; }
    } },
    module: { exports: {} }, JSON, Date, Intl, Number, Array, Object, Math, Error, String, RegExp
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/manual.js"), "utf8"), context);
  const { draftFingerprint } = context.module.exports;
  const original = { date: "2026-11-23", kind: "intervals_override", note: "do not overwrite",
    intervals: [{start:"08:00", end:"10:01"}], present: true };
  const edited = {...original, intervals: [{start:"08:30", end:"10:02"}]};
  const baseline = draftFingerprint(original, true);
  const undo = createDraftUndo(); undo.record(original, edited);
  lang = "en";
  assert.equal(draftFingerprint({...original, intervals:[{start:"08:00", end:"10:05"}]}, true), baseline);
  assert.notEqual(draftFingerprint(edited, true), baseline);
  assert.deepEqual(undo.peek(original.date), original);
  assert.equal(dictionary["至今"], "Present");
  lang = "zh";
  assert.equal(draftFingerprint(original, true), baseline);
  assert.deepEqual(undo.peek(original.date), original);
});
