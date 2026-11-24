"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function page({ locale = "en-US", saved = null, broken = false } = {}) {
  const store = new Map(saved === null ? [] : [["hourly-rate-language", saved]]);
  const windowHandlers = {}, documentHandlers = {}, events = [];
  const label = { nodeValue: "  设置  ", isConnected: true, parentElement: { tagName: "BUTTON", hasAttribute: () => false } };
  const dynamic = { nodeValue: "等待记录", isConnected: true, parentElement: { tagName: "SPAN", hasAttribute: () => false } };
  const title = { textContent: "工作占用 · 时薪仪表盘", dataset: {} };
  const attr = { isConnected: true, values: { "aria-label": "打开本机设置" }, getAttribute(k) { return this.values[k] ?? null; }, setAttribute(k,v) { this.values[k] = v; } };
  const control = { value: "", handlers: {}, addEventListener(name, fn) { this.handlers[name] = fn; } };
  const document = {
    body: {}, documentElement: { dataset: {} },
    createTreeWalker() { let i = 0, items = [label, dynamic]; return { nextNode: () => items[i++] || null }; },
    querySelector(q) { return q === "title" ? title : null; },
    querySelectorAll(q) { return q === "[aria-label], [placeholder], [title]" ? [attr] : []; },
    getElementById(id) { return id === "language-mode" ? control : null; },
    addEventListener(name, fn) { documentHandlers[name] = fn; }
  };
  const window = {
    navigator: { language: locale },
    localStorage: { getItem(k) { if (broken) throw Error("denied"); return store.get(k) ?? null; }, setItem(k,v) { if (broken) throw Error("denied"); store.set(k,v); } },
    addEventListener(name, fn) { windowHandlers[name] = fn; }, dispatchEvent(event) { events.push(event); }
  };
  class CustomEvent { constructor(type, options) { this.type=type; this.detail=options.detail; } }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/i18n.js"), "utf8"), { window, document, CustomEvent, NodeFilter: { SHOW_TEXT: 4 } });
  return { window, document, documentHandlers, windowHandlers, events, store, label, dynamic, title, attr, control, ready() { documentHandlers.DOMContentLoaded(); } };
}

test("defaults to system language and translates static content without changing settings", () => {
  const p = page(); p.ready();
  assert.equal(p.window.hourlyI18n.preference(), "system");
  assert.equal(p.window.hourlyI18n.language(), "en");
  assert.equal(p.document.documentElement.lang, "en");
  assert.equal(p.label.nodeValue, "  Settings  ");
  assert.equal(p.attr.values["aria-label"], "Open local settings");
  assert.equal(p.store.has("hourly-rate-language"), false);
});

test("selection persists, broadcasts, and preserves a changed dynamic node", () => {
  const p = page({ locale:"zh-CN" }); p.ready();
  assert.equal(p.window.hourlyI18n.language(), "zh");
  p.dynamic.nodeValue = "用户修改了内容";
  p.window.hourlyI18n.setPreference("en");
  assert.equal(p.store.get("hourly-rate-language"), "en");
  assert.equal(p.label.nodeValue, "  Settings  ");
  assert.equal(p.dynamic.nodeValue, "用户修改了内容");
  assert.equal(p.events.at(-1).type, "hourly:language-change");
  p.window.hourlyI18n.setPreference("zh");
  assert.equal(p.label.nodeValue, "  设置  ");
  assert.equal(p.dynamic.nodeValue, "用户修改了内容");
});

test("registered dictionaries interpolate safely and can refresh existing static content", () => {
  const p = page(); p.ready();
  p.window.hourlyI18n.register({"等待记录":"Waiting for data", "你好 {name}":"Hello {name}"});
  assert.equal(p.dynamic.nodeValue, "Waiting for data");
  assert.equal(p.window.hourlyI18n.t("你好 {name}", { name:"Alice" }), "Hello Alice");
  assert.equal(p.window.hourlyI18n.t("你好 {name}"), "Hello {name}");
  assert.equal(p.window.hourlyI18n.t("未收录"), "未收录");
  assert.equal(p.window.hourlyI18n.t(undefined), undefined);
  assert.equal(p.window.hourlyI18n.t(null), null);
});

test("system changes, cross-tab changes and unavailable storage are handled", () => {
  const p = page({ broken:true }); p.ready();
  p.window.hourlyI18n.setPreference("zh");
  assert.equal(p.window.hourlyI18n.language(), "zh");
  p.window.navigator.language = "en-GB";
  p.windowHandlers.languagechange(); assert.equal(p.window.hourlyI18n.language(), "zh");
  p.window.hourlyI18n.setPreference("system");
  assert.equal(p.window.hourlyI18n.language(), "en");
  p.windowHandlers.storage({ key:"hourly-rate-language", newValue:"zh" });
  assert.equal(p.window.hourlyI18n.language(), "zh");
  assert.equal(p.window.hourlyI18n.setPreference("invalid"), false);
});
