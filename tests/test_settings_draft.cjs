"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { captureSettingsDraft, savedSettingsBaseline, supportedSettingsProvider } = require("../static/app.js");

function settingsForm() {
  const elements = {};
  for (const key of ["annual_salary", "currency", "timezone", "provider", "service_id", "status_script_path", "night_pause_start", "night_pause_end", "theoretical_daily_hours", "screen_alert_hours"]) elements[key] = { value: key };
  for (const key of ["tracking_enabled", "pause_on_sleep", "night_pause_enabled", "screen_alert_enabled"]) elements[key] = { checked: false };
  const days = [{ checked: true }, { checked: false }];
  const form = { elements, querySelectorAll: () => days };
  const cells = { ".salary-effective-date": {value:"2026-01-01"}, ".salary-period-amount": {value:"100000"} };
  const history = { children: [{querySelector: selector => cells[selector]}] };
  return {form, history, cells, days};
}

test("settings drafts capture checkbox, date and salary edits without tracking immediate actions", () => {
  const s = settingsForm(), initial = captureSettingsDraft(s.form, s.history);
  s.form.elements.autostart = { checked: true };
  assert.deepEqual(captureSettingsDraft(s.form, s.history), initial);
  s.cells[".salary-period-amount"].value = "150000";
  assert.notDeepEqual(captureSettingsDraft(s.form, s.history), initial);
  assert.equal(initial.salary_history[0][1], "100000");
  s.cells[".salary-period-amount"].value = "100000";
  s.days[1].checked = true;
  assert.notDeepEqual(captureSettingsDraft(s.form, s.history), initial);
});

test("saving visible settings retains unsaved hidden salary and time drafts", () => {
  const s = settingsForm(), original = captureSettingsDraft(s.form, s.history);
  s.form.elements.annual_salary.value = "200000";
  s.form.elements.night_pause_start.value = "01:00";
  s.form.elements.timezone.value = "UTC";
  const submitted = captureSettingsDraft(s.form, s.history);
  const after = savedSettingsBaseline(original, submitted, true, true);
  assert.equal(after.annual_salary, original.annual_salary);
  assert.equal(after.night_pause_start, original.night_pause_start);
  assert.equal(after.timezone, "UTC");
  assert.notDeepEqual(after, submitted);
  assert.deepEqual(savedSettingsBaseline(after, submitted, false, false), submitted);
});

test("edits made during an in-flight save remain unsaved", () => {
  const s = settingsForm(), initial = captureSettingsDraft(s.form, s.history);
  s.form.elements.timezone.value = "UTC";
  const submitted = captureSettingsDraft(s.form, s.history);
  s.form.elements.timezone.value = "Europe/Paris";
  const baseline = savedSettingsBaseline(initial, submitted, false, false);
  assert.notDeepEqual(captureSettingsDraft(s.form, s.history), baseline);
});

test("verified system is available while unknown old providers cannot be saved", () => {
  for (const value of ["script", "system", "verified_system", "disabled", "cisco"]) assert.equal(supportedSettingsProvider(value), true);
  for (const value of ["", "unknown-legacy-provider", "__proto__"]) assert.equal(supportedSettingsProvider(value), false);
});
