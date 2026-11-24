"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function page({ saved = null, savedV2 = null, search = "", storageThrows = false } = {}) {
  const values = new Map();
  if (saved !== null) values.set("hourly-privacy-hidden", saved);
  if (savedV2 !== null) values.set("hourly-privacy-v2", savedV2);
  const handlers = new Map();
  const events = [];
  const root = { dataset: {} };
  const window = {
    localStorage: {
      getItem: key => { if (storageThrows) throw Error("unavailable"); return values.get(key) ?? null; },
      setItem: (key, value) => { if (storageThrows) throw Error("unavailable"); values.set(key, value); },
    },
    location: { search, href: "http://127.0.0.1:8765/" + search },
    history: { replaceState() {} },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener(name, fn) { handlers.set(name, [...(handlers.get(name) || []), fn]); },
    dispatchEvent(event) { events.push(event); },
  };
  const document = { documentElement: root, addEventListener() {} };
  class CustomEvent { constructor(type, options) { this.type = type; this.detail = options.detail; } }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/theme.js"), "utf8"),
    { window, document, CustomEvent, URL, URLSearchParams });
  const storage = event => (handlers.get("storage") || []).forEach(handler => handler(event));
  return { values, root, window, storage, events };
}

test("legacy hidden preferences migrate both protections before paint", () => {
  const p = page({ saved: "1" });
  assert.equal(p.root.dataset.privacyNumbers, "hidden");
  assert.equal(p.root.dataset.privacyTime, "hidden");
  assert.deepEqual(JSON.parse(p.values.get("hourly-privacy-v2")), { numbers: true, time: true });
});

test("clearing or corrupting storage does not silently reveal hidden values", () => {
  const p = page({ saved: "1" });
  p.storage({ key: null, newValue: null });
  assert.equal(p.root.dataset.privacy, "hidden");
  p.storage({ key: "hourly-privacy-v2", newValue: null });
  assert.equal(p.root.dataset.privacy, "hidden");
  p.storage({ key: "hourly-privacy-v2", newValue: "invalid" });
  assert.equal(p.root.dataset.privacy, "hidden");
  p.storage({ key: "hourly-privacy-v2", newValue: '{"numbers":false,"time":false}' });
  assert.equal(p.root.dataset.privacy, "shown");
});

test("a hidden navigation preference persists when storage is available again", () => {
  const p = page({ saved: "0", search: "?privacy=1" });
  assert.equal(p.root.dataset.privacy, "hidden");
  assert.equal(p.values.get("hourly-privacy-hidden"), "1");
  assert.deepEqual(JSON.parse(p.values.get("hourly-privacy-v2")), { numbers: true, time: true });
});

test("each privacy switch is independent and sends complete state", () => {
  const p = page();
  p.window.hourlyPrivacy.setNumbersHidden(true);
  assert.equal(p.window.hourlyPrivacy.isNumbersHidden(), true);
  assert.equal(p.window.hourlyPrivacy.isTimeHidden(), false);
  assert.equal(p.root.dataset.privacyNumbers, "hidden");
  assert.equal(p.root.dataset.privacyTime, "shown");
  assert.deepEqual(JSON.parse(p.values.get("hourly-privacy-v2")), { numbers: true, time: false });
  assert.equal(p.values.get("hourly-privacy-hidden"), "1");
  assert.equal(p.events.at(-1).detail.numbersHidden, true);
  assert.equal(p.events.at(-1).detail.timeHidden, false);
  p.window.hourlyPrivacy.setTimeHidden(true);
  p.window.hourlyPrivacy.setNumbersHidden(false);
  assert.equal(p.window.hourlyPrivacy.isNumbersHidden(), false);
  assert.equal(p.window.hourlyPrivacy.isTimeHidden(), true);
  assert.equal(p.window.hourlyPrivacy.isHidden(), true);
  p.window.hourlyPrivacy.setTimeHidden(false);
  assert.equal(p.window.hourlyPrivacy.isHidden(), false);
  assert.equal(p.values.get("hourly-privacy-hidden"), "0");
});

test("cross-tab state is atomic and the legacy notification cannot overwrite it", () => {
  const p = page({ saved: "1" });
  const updated = '{"numbers":true,"time":false}';
  p.values.set("hourly-privacy-v2", updated);
  p.storage({ key: "hourly-privacy-v2", newValue: updated });
  p.storage({ key: "hourly-privacy-hidden", newValue: "1" });
  assert.equal(p.root.dataset.privacyNumbers, "hidden");
  assert.equal(p.root.dataset.privacyTime, "shown");
});

test("URL fallback preserves each independent choice without browser storage", () => {
  for (const [value, numbers, time] of [["numbers", true, false], ["time", false, true], ["1", true, true]]) {
    const p = page({ search: "?privacy=" + value, storageThrows: true });
    assert.equal(p.window.hourlyPrivacy.canPersist(), false);
    assert.equal(p.window.hourlyPrivacy.isNumbersHidden(), numbers);
    assert.equal(p.window.hourlyPrivacy.isTimeHidden(), time);
    assert.equal(p.window.hourlyPrivacy.fallbackValue(), value);
  }
});

test("a partial navigation fallback cannot reveal another saved hidden dimension", () => {
  const both = '{"numbers":true,"time":true}';
  for (const fallback of ["numbers", "time"]) {
    const p = page({ savedV2: both, search: "?privacy=" + fallback });
    assert.equal(p.window.hourlyPrivacy.isNumbersHidden(), true);
    assert.equal(p.window.hourlyPrivacy.isTimeHidden(), true);
    assert.equal(p.root.dataset.privacyNumbers, "hidden");
    assert.equal(p.root.dataset.privacyTime, "hidden");
    assert.deepEqual(JSON.parse(p.values.get("hourly-privacy-v2")), { numbers: true, time: true });
  }
});

test("navigation fallback adds protection to a different saved hidden dimension", () => {
  for (const [stored, fallback] of [
    ['{"numbers":false,"time":true}', "numbers"],
    ['{"numbers":true,"time":false}', "time"],
  ]) {
    const p = page({ savedV2: stored, search: "?privacy=" + fallback });
    assert.equal(p.window.hourlyPrivacy.isNumbersHidden(), true);
    assert.equal(p.window.hourlyPrivacy.isTimeHidden(), true);
  }
});

test("a malformed saved v2 preference fails closed", () => {
  const p = page({ savedV2: "broken" });
  assert.equal(p.window.hourlyPrivacy.isNumbersHidden(), true);
  assert.equal(p.window.hourlyPrivacy.isTimeHidden(), true);
});
