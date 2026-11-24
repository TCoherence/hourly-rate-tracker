"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function makePage({ hidden = false, saved = null, savedV2 = null, query = "", storageThrows = false, sharedPrivacy = null, sharedI18n = null, fetchImpl }) {
  const values = new Map(hidden ? [["hourly-privacy-hidden", "1"]] : []);
  if (saved !== null) values.set("hourly-privacy-hidden", saved);
  if (savedV2 !== null) values.set("hourly-privacy-v2", JSON.stringify(savedV2));
  const handlers = new Map();
  const nodes = new Map();
  function node() {
    return { hidden: false, disabled: false, textContent: "", children: [],
      addEventListener() {}, append(...items) { this.children.push(...items); },
      replaceChildren(...items) { this.children = items; } };
  }
  for (const id of ["log-privacy", "log-entries", "log-empty", "log-error", "log-status", "refresh-log"]) nodes.set(id, node());
  const links = [node(), node()];
  const window = { location: { hash: "", pathname: "/logs.html", search: query },
    addEventListener(name, fn) { handlers.set(name, fn); } };
  if (sharedPrivacy) window.hourlyPrivacy = sharedPrivacy;
  if (sharedI18n) window.hourlyI18n = sharedI18n;
  const context = { window, document: { getElementById: id => nodes.get(id), createElement: node,
      querySelectorAll: () => links },
    localStorage: { getItem: key => { if (storageThrows) throw Error("unavailable"); return values.get(key) ?? null; } },
    sessionStorage: { getItem: () => "" }, history: { replaceState() {} },
    URLSearchParams, Date, JSON, Number, setInterval() {}, fetch: fetchImpl };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/logs.js"), "utf8"), context);
  return { nodes, values, handlers, links };
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test("cross-tab language changes rerender logs without exposing hidden details", async () => {
  let language = "zh";
  const dictionary = {};
  const i18n = { register: entries => Object.assign(dictionary, entries), language: () => language,
    t: text => language === "en" ? dictionary[text] || text : text };
  const page = makePage({ sharedI18n: i18n, savedV2: { numbers: true, time: false }, fetchImpl: async () => ({
    ok: true, json: async () => ({ entries: [{ timestamp: "2026-01-01T01:00:00Z", state: "connected", provider: "script", message: "private" }] })
  }) });
  await flush();
  assert.equal(page.nodes.get("log-entries").children[0].children[0].children[1].textContent, "VPN 已连接");
  language = "en";
  page.handlers.get("hourly:language-change")();
  await flush();
  const item = page.nodes.get("log-entries").children[0];
  assert.equal(item.children[0].children[1].textContent, "VPN connected");
  assert.equal(item.children[1].textContent, "***");
});

test("generic migrated sources retain readable labels and unknown names are not exposed", async () => {
  const names = ["legacy_script", "verified_system", "unknown-company-provider", "__proto__"];
  const page = makePage({ fetchImpl: async () => ({ ok: true, json: async () => ({ entries: names.map(provider => ({ timestamp: "2026-01-01T01:00:00Z", state: "connected", provider, message: "test" })) }) }) });
  await flush();
  const labels = page.nodes.get("log-entries").children.map(item => item.children[0].children[2].textContent);
  assert.deepEqual(labels, ["其他来源", "其他来源", "需核对的系统 VPN", "本机状态脚本（旧记录）"]);
});

test("removing or clearing the preference cannot reveal hidden logs; explicit 0 can", async () => {
  let calls = 0;
  const page = makePage({ hidden: true, fetchImpl: async () => {
    calls++;
    return { ok: true, json: async () => ({ entries: [] }) };
  } });
  assert.equal(calls, 0);
  assert.equal(page.nodes.get("log-privacy").hidden, false);
  assert.equal(page.nodes.get("refresh-log").disabled, true);
  assert.equal(page.links[0].href, "/?privacy=1");
  page.values.delete("hourly-privacy-hidden");
  page.handlers.get("storage")({ key: "hourly-privacy-hidden", newValue: null });
  await flush();
  assert.equal(calls, 0);
  assert.equal(page.nodes.get("log-privacy").hidden, false);
  page.handlers.get("storage")({ key: null, newValue: null });
  await flush();
  assert.equal(calls, 0);
  assert.equal(page.nodes.get("log-privacy").hidden, false);
  page.values.set("hourly-privacy-hidden", "0");
  page.handlers.get("storage")({ key: "hourly-privacy-hidden", newValue: "0" });
  await flush();
  assert.equal(calls, 1);
  assert.equal(page.nodes.get("log-privacy").hidden, true);
  assert.equal(page.links[0].href, "/");
});

test("a response arriving after hiding cannot put log details back", async () => {
  let finish;
  const page = makePage({ fetchImpl: () => new Promise(resolve => { finish = resolve; }) });
  page.values.set("hourly-privacy-hidden", "1");
  page.handlers.get("storage")({ key: "hourly-privacy-hidden", newValue: "1" });
  finish({ ok: true, json: async () => ({ entries: [{ timestamp: "2026-01-01T01:00:00Z", state: "connected", provider: "script", message: "private" }] }) });
  await flush();
  assert.equal(page.nodes.get("log-entries").children.length, 0);
  assert.equal(page.nodes.get("log-privacy").hidden, false);
  assert.equal(page.nodes.get("refresh-log").disabled, true);
});

test("privacy query protects standalone logs when storage is unavailable", () => {
  let calls = 0;
  const page = makePage({ query: "?privacy=1", storageThrows: true, fetchImpl: () => { calls++; } });
  assert.equal(calls, 0);
  assert.equal(page.nodes.get("log-privacy").hidden, false);
});

test("privacy query overrides an old visible preference when saving failed", () => {
  let calls = 0;
  const page = makePage({ query: "?privacy=1", saved: "0", fetchImpl: () => { calls++; } });
  assert.equal(calls, 0);
  assert.equal(page.nodes.get("log-privacy").hidden, false);
});

test("shared privacy changes reveal logs only after an explicit request", async () => {
  let calls = 0;
  let hidden = true;
  const page = makePage({ sharedPrivacy: { isNumbersHidden: () => false, isTimeHidden: () => hidden }, fetchImpl: async () => {
    calls++;
    return { ok: true, json: async () => ({ entries: [] }) };
  } });
  assert.equal(calls, 0);
  assert.equal(page.nodes.get("log-privacy").hidden, false);
  hidden = false;
  page.handlers.get("hourly:privacy-change")({ detail: { hidden: false, numbersHidden: false, timeHidden: false } });
  await flush();
  assert.equal(calls, 1);
  assert.equal(page.nodes.get("log-privacy").hidden, true);
});

test("numbers-only privacy keeps timestamps but masks arbitrary log messages", async () => {
  const page = makePage({ savedV2: { numbers: true, time: false }, fetchImpl: async () => ({
    ok: true, json: async () => ({ entries: [{ timestamp: "2026-01-01T01:00:00Z", state: "connected", provider: "script", message: "金额 12345" }] })
  }) });
  await flush();
  assert.equal(page.nodes.get("log-privacy").hidden, true);
  assert.equal(page.nodes.get("refresh-log").disabled, false);
  assert.equal(page.nodes.get("log-entries").children[0].children[1].textContent, "***");
  assert.equal(page.links[0].href, "/?privacy=numbers");
});

test("time-only fallback hides logs without converting to both flags", () => {
  let calls = 0;
  const page = makePage({ query: "?privacy=time", storageThrows: true, fetchImpl: () => { calls++; } });
  assert.equal(calls, 0);
  assert.equal(page.nodes.get("log-privacy").hidden, false);
  assert.equal(page.links[0].href, "/?privacy=time");
});

test("switching numbers privacy clears stale messages and renders masked data", async () => {
  let numbersHidden = false;
  const page = makePage({ sharedPrivacy: { isNumbersHidden: () => numbersHidden, isTimeHidden: () => false },
    fetchImpl: async () => ({ ok: true, json: async () => ({ entries: [{ timestamp: "2026-01-01T01:00:00Z", state: "connected", provider: "script", message: "金额 12345" }] }) }) });
  await flush();
  assert.equal(page.nodes.get("log-entries").children[0].children[1].textContent, "金额 12345");
  numbersHidden = true;
  page.handlers.get("hourly:privacy-change")({ detail: { hidden: true, numbersHidden: true, timeHidden: false } });
  assert.equal(page.nodes.get("log-entries").children.length, 0);
  await flush();
  assert.equal(page.nodes.get("log-entries").children[0].children[1].textContent, "***");
});
