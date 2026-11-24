"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function calendar({ fetchImpl } = {}) {
  let numbers = false, time = false, observer, language = "zh";
  const dictionary = {};
  const handlers = new Map();
  const classes = new Set(["selected"]);
  const day = {
    dataset: { date: "2026-11-16" }, attributes: {}, small: null,
    classList: { add: x => classes.add(x), remove: (...xs) => xs.forEach(x => classes.delete(x)), contains: x => classes.has(x) },
    querySelector: tag => tag === "small" ? day.small : null,
    append: node => { day.small = node; },
    setAttribute: (name, value) => { day.attributes[name] = value; },
  };
  const grid = { querySelectorAll: () => [day] };
  let details;
  const document = {
    documentElement: { dataset: {} },
    getElementById(id) {
      if (id === "manual-calendar-days") return grid;
      if (id === "manual-selected-label") return { parentElement: { after: node => { details = node; } } };
      if (id === "open-manual") return { addEventListener() {} };
      throw Error("unexpected element: " + id);
    },
    createElement: () => ({ className: "", textContent: "", setAttribute() {} }),
  };
  const window = {
    hourlyPrivacy: { isNumbersHidden: () => numbers, isTimeHidden: () => time },
    hourlyI18n: { register: values => Object.assign(dictionary, values), t: key => language === "en" ? dictionary[key] || key : key, language: () => language },
    addEventListener: (name, fn) => handlers.set(name, fn),
  };
  class MutationObserver { constructor(fn) { observer = fn; } observe() {} }
  const data = { days: [{ date: "2026-11-16", status: "partial", work_hours: 7.25, vpn_work_hours: 6, manual_kind: "daily_total" }] };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/history-calendar.js"), "utf8"), {
    window, document, MutationObserver, sessionStorage: { getItem: () => "" }, localStorage: { getItem: () => null },
    fetch: fetchImpl || (async () => ({ ok: true, json: async () => data })), JSON, Number, Map, Date, encodeURIComponent,
  });
  return {
    day, details: () => details, render: () => observer(),
    change(n, t) { numbers = n; time = t; handlers.get("hourly:privacy-change")({ detail: { numbersHidden: n, timeHidden: t } }); },
    language(next) { language = next; handlers.get("hourly:language-change")(); },
    saved() { handlers.get("hourly:manual-change")(); },
    data,
  };
}
const flush = () => new Promise(resolve => setImmediate(resolve));

test("money privacy keeps calendar hours; time privacy masks hours while retaining color", async () => {
  const c = calendar(); c.render(); await flush();
  assert.equal(c.day.small.textContent, "7.25h");
  c.change(true, false);
  assert.equal(c.day.small.textContent, "7.25h");
  assert.match(c.day.attributes["aria-label"], /7\.25/);
  c.change(true, true);
  assert.equal(c.day.small.textContent, "");
  assert.doesNotMatch(c.day.attributes["aria-label"], /7\.25/);
  assert.equal(c.day.classList.contains("history-level-3"), true);
  assert.doesNotMatch(c.details().textContent, /7\.25|6 小时/);
  c.change(true, false);
  assert.equal(c.day.small.textContent, "7.25h");
});

test("switching calendar language keeps hours and privacy intact", async () => {
  const c = calendar(); c.render(); await flush();
  assert.match(c.details().textContent, /当天总工时/);
  c.language("en");
  assert.match(c.details().textContent, /Total work time/);
  assert.doesNotMatch(c.details().textContent, /。/);
  assert.equal(c.day.small.textContent, "7.25h");
  c.change(false, true);
  assert.equal(c.day.small.textContent, "");
  assert.doesNotMatch(c.day.attributes["aria-label"], /7\.25/);
  c.language("zh");
  assert.match(c.details().textContent, /隐藏/);
  assert.equal(c.day.small.textContent, "");
});

test("saving reloads the calendar and ignores a stale response from before the save", async () => {
  const requests = [];
  const c = calendar({ fetchImpl: () => new Promise(resolve => requests.push(resolve)) });
  c.render();
  c.saved();
  assert.equal(requests.length, 2);
  const result = hours => ({ ok: true, json: async () => ({ days: [{ date: "2026-11-16", status: "partial", work_hours: hours, vpn_work_hours: 0, manual_kind: "intervals_override" }] }) });
  requests[1](result(8.5));
  await flush();
  assert.equal(c.day.small.textContent, "8.5h");
  requests[0](result(2));
  await flush();
  assert.equal(c.day.small.textContent, "8.5h");
  assert.equal(c.day.classList.contains("history-level-3"), true);
});

test("switching months and returning ignores an older request for the same month", async () => {
  const requests = [];
  const c = calendar({ fetchImpl: () => new Promise(resolve => requests.push(resolve)) });
  c.render();
  c.day.dataset.date = "2026-10-16"; c.render();
  c.day.dataset.date = "2026-11-16"; c.render();
  assert.equal(requests.length, 3);
  const result = hours => ({ ok: true, json: async () => ({ days: [{ date: "2026-11-16", status: "partial", work_hours: hours, vpn_work_hours: 0 }] }) });
  requests[2](result(8.5));
  await flush();
  assert.equal(c.day.small.textContent, "8.5h");
  requests[0](result(2));
  await flush();
  assert.equal(c.day.small.textContent, "8.5h");
  assert.equal(c.day.classList.contains("history-level-3"), true);
});

test("a calendar response arriving after time is hidden never displays hours", async () => {
  let finish;
  const c = calendar({ fetchImpl: () => new Promise(resolve => { finish = resolve; }) });
  c.render(); c.change(false, true);
  finish({ ok: true, json: async () => c.data });
  await flush();
  assert.equal(c.day.small.textContent, "");
  assert.doesNotMatch(c.day.attributes["aria-label"], /7\.25/);
  assert.equal(c.day.classList.contains("history-level-3"), true);
});
