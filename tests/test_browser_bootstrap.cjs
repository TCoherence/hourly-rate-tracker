"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

test("existing static entry initializes language, translations and undo before the calendar", () => {
  const handlers = {}, values = new Map();
  const window = {
    navigator: { language: "en-US" },
    localStorage: { getItem: k => values.get(k) ?? null, setItem: (k, v) => values.set(k, v) },
    addEventListener(name, fn) { (handlers[name] ||= []).push(fn); },
    dispatchEvent() {},
  };
  const document = {
    body: null, documentElement: { dataset: {} },
    addEventListener() {}, getElementById() { return null; },
    querySelector() { return null; }, querySelectorAll() { return []; },
  };
  class CustomEvent { constructor(type, options) { this.type = type; this.detail = options.detail; } }
  const context = vm.createContext({ window, document, CustomEvent, NodeFilter: { SHOW_TEXT: 4 } });
  const bundle = fs.readFileSync(path.join(__dirname, "../static/history-calendar.js"), "utf8");
  vm.runInContext(bundle, context);
  assert.equal(window.hourlyI18n.language(), "en");
  assert.equal(window.hourlyI18n.t("正在记录工时"), "Tracking work time");
  assert.equal(typeof window.hourlyDraftUndo.createDraftUndo, "function");
  assert.equal(window.HourlyHistoryCalendar.level(5), 2);

  // An older cached HTML document can still request the separate locale
  // script after the bundle. It must not replace state or add listeners.
  window.hourlyI18n.setPreference("zh");
  const instance = window.hourlyI18n, storageListeners = handlers.storage.length;
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/i18n.js"), "utf8"), context);
  assert.equal(window.hourlyI18n, instance);
  assert.equal(window.hourlyI18n.language(), "zh");
  assert.equal(handlers.storage.length, storageListeners);
});
