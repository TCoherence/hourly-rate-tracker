"use strict";

(() => {
  const $ = id => document.getElementById(id);
  const t = value => window.hourlyI18n ? window.hourlyI18n.t(value) : value;
  const locale = () => window.hourlyI18n && window.hourlyI18n.language() === "en" ? "en-US" : "zh-CN";
  if (window.hourlyI18n) window.hourlyI18n.register({
    "实时 VPN 日志 · 工作占用": "Live VPN log · Time / Cost", "工作占用": "Time / Cost", "返回仪表盘": "Back to dashboard",
    "实时 VPN 日志": "Live VPN log", "每 15 秒检测一次 VPN，仅在状态变化时新增日志。页面每 3 秒更新，最近的记录显示在最上方。": "VPN status is checked every 15 seconds. A log entry is added only when the status changes. This page refreshes every 3 seconds, with the newest entries first.",
    "最近 VPN 状态变化": "Recent VPN status changes", "正在读取本机日志…": "Loading local log…", "立即刷新": "Refresh now",
    "时间已隐藏，日志详情暂时不可见。请回到仪表盘选择显示时间后再查看。": "Time is hidden, so log details are unavailable. Return to the dashboard and show time to view them.",
    "还没有状态日志。启用计时后，首次检测会出现在这里。": "No status entries yet. The first check will appear here after tracking is enabled.",
    "仅显示此 Mac 最近 30 条状态变化，不读取流量或节点信息，也不会改变 VPN 连接。": "Shows the last 30 status changes on this Mac. No traffic or node information is read, and the VPN connection is not changed.",
    "VPN 已连接": "VPN connected", "已断开 · 不计自动工时": "Disconnected · not tracked", "状态未知 · 不计自动工时": "Status unknown · not tracked", "采集未开启": "Tracking disabled", "Mac 进入睡眠": "Mac went to sleep", "Mac 已唤醒 · 恢复检测": "Mac woke · checks resumed",
    "本机状态脚本": "Local status script", "本机状态脚本（旧记录）": "Local status script (older entry)", "需核对的系统 VPN": "System VPN requiring verification", "系统 VPN": "System VPN", "未启用": "Disabled", "系统睡眠": "System sleep", "其他来源": "Other source", "隐私模式已开启": "Privacy mode is on",
    "此浏览器尚未授权或服务已重启。请通过 start-hourly-rate.command 打开一次仪表盘，再打开实时日志。": "This browser is not authorized or the service has restarted. Open the dashboard using start-hourly-rate.command, then return to the live log.",
    "暂时无法读取本机日志，请确认应用仍在运行。": "Could not read the local log. Check that the app is running.", "自动更新中 · 最近检查 ": "Updating automatically · Last checked ", "等待恢复": "Waiting for connection"
  });
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  let token = fragment.get("access") || "";
  try {
    if (token) sessionStorage.setItem("hourly-access", token);
    else token = sessionStorage.getItem("hourly-access") || "";
  } catch (_) { /* The launch token and browser session work without storage. */ }
  if (window.location.hash) history.replaceState(null, "", window.location.pathname);
  function authHeaders() {
    const headers = token ? { "X-Session-Token": token } : {};
    try {
      const saved = JSON.parse(localStorage.getItem("hourly-browser-auth-v1") || "null");
      if (saved && typeof saved.token === "string" && Number.isFinite(saved.expires_at) && saved.expires_at * 1000 > Date.now()) headers["X-Browser-Token"] = saved.token;
    } catch (_) { /* Existing browser session remains usable. */ }
    return headers;
  }
  const states = { connected: "VPN 已连接", disconnected: "已断开 · 不计自动工时", unknown: "状态未知 · 不计自动工时", disabled: "采集未开启", sleep: "Mac 进入睡眠", wake: "Mac 已唤醒 · 恢复检测" };
  const providers = { script: "本机状态脚本", legacy_script: "本机状态脚本（旧记录）", verified_system: "需核对的系统 VPN", system: "系统 VPN", cisco: "Cisco", disabled: "未启用", system_power: "系统睡眠" };
  let busy = false;
  let previous = "";
  const queryPrivacy = new URLSearchParams(window.location.search).get("privacy");
  let fallbackNumbers = queryPrivacy === "1" || queryPrivacy === "numbers";
  let fallbackTime = queryPrivacy === "1" || queryPrivacy === "time";
  let privacyState = { numbers: fallbackNumbers, time: fallbackTime };
  let previousNumbers = null;
  function parsePrivacy(value) {
    try {
      const data = JSON.parse(value);
      return data && typeof data.numbers === "boolean" && typeof data.time === "boolean" ? data : null;
    } catch (_) { return null; }
  }
  function currentPrivacy() {
    const shared = window.hourlyPrivacy;
    if (shared && typeof shared.isTimeHidden === "function" && typeof shared.isNumbersHidden === "function") {
      privacyState = { numbers: shared.isNumbersHidden(), time: shared.isTimeHidden() };
      return privacyState;
    }
    try {
      const raw = localStorage.getItem("hourly-privacy-v2");
      const saved = parsePrivacy(raw);
      if (saved) privacyState = { numbers: saved.numbers || fallbackNumbers, time: saved.time || fallbackTime };
      else if (raw !== null) privacyState = { numbers: true, time: true };
      else {
        const legacy = localStorage.getItem("hourly-privacy-hidden");
        if (legacy === "1") privacyState = { numbers: true, time: true };
        else if (legacy === "0") privacyState = { numbers: fallbackNumbers, time: fallbackTime };
      }
    } catch (_) { /* Keep the last known state when storage is unavailable. */ }
    return privacyState;
  }
  function privacyHidden() { return currentPrivacy().time; }
  function numbersHidden() { return currentPrivacy().numbers; }
  function applyPrivacy() {
    const state = currentPrivacy(), hidden = state.time;
    const fallback = state.numbers && state.time ? "1" : state.numbers ? "numbers" : state.time ? "time" : "";
    document.querySelectorAll("[data-dashboard-link]").forEach(link => { link.href = fallback ? "/?privacy=" + fallback : "/"; });
    // Remove existing messages synchronously before the newly private render.
    if (previousNumbers !== state.numbers) { $("log-entries").replaceChildren(); previous = ""; previousNumbers = state.numbers; }
    $("log-privacy").hidden = !hidden;
    if (hidden) {
      $("log-entries").replaceChildren();
      $("log-empty").hidden = true;
      $("log-error").hidden = true;
      $("log-status").textContent = t("隐私模式已开启");
      $("refresh-log").disabled = true;
      previous = "";
    } else {
      $("refresh-log").disabled = busy;
      refresh();
    }
  }
  function text(tag, className, value) {
    const el = document.createElement(tag);
    el.className = className;
    el.textContent = value;
    return el;
  }
  async function refresh() {
    if (privacyHidden()) return;
    if (busy) return;
    busy = true;
    $("refresh-log").disabled = true;
    try {
      const response = await fetch("/api/status-log", { cache: "no-store", credentials: "same-origin", headers: authHeaders() });
      if (response.status === 401 || response.status === 403) throw new Error(t("此浏览器尚未授权或服务已重启。请通过 start-hourly-rate.command 打开一次仪表盘，再打开实时日志。"));
      if (!response.ok) throw new Error(t("暂时无法读取本机日志，请确认应用仍在运行。"));
      const result = await response.json();
      if (privacyHidden()) { applyPrivacy(); return; }
      const signature = JSON.stringify(result.entries);
      if (signature !== previous) {
        const entries = result.entries.slice().reverse().map(entry => {
          const item = text("li", "log-entry", "");
          const meta = text("div", "log-meta", "");
          const time = new Date(entry.timestamp).toLocaleString(locale(), { hour12: false });
          const provider = Object.prototype.hasOwnProperty.call(providers, entry.provider) ? providers[entry.provider] : "其他来源";
          meta.append(text("time", "", time), text("span", "log-state", t(states[entry.state] || entry.state)), text("span", "", t(provider)));
          item.append(meta, text("p", "log-message", numbersHidden() ? "***" : t(entry.message)));
          return item;
        });
        $("log-entries").replaceChildren(...entries);
        $("log-empty").hidden = entries.length > 0;
        previous = signature;
      }
      $("log-status").textContent = t("自动更新中 · 最近检查 ") + new Date().toLocaleTimeString(locale(), { hour12: false });
      $("log-error").hidden = true;
    } catch (error) {
      if (privacyHidden()) { applyPrivacy(); return; }
      $("log-error").textContent = error.message;
      $("log-error").hidden = false;
      $("log-status").textContent = t("等待恢复");
    } finally {
      busy = false;
      $("refresh-log").disabled = privacyHidden();
    }
  }
  $("refresh-log").addEventListener("click", refresh);
  window.addEventListener("storage", event => {
    if (event.key === "hourly-privacy-v2" || event.key === "hourly-privacy-hidden" || event.key === null) {
      const value = event.key === "hourly-privacy-v2" ? parsePrivacy(event.newValue) : null;
      if (value) { fallbackNumbers = false; fallbackTime = false; privacyState = { numbers: value.numbers, time: value.time }; }
      else if (event.key === "hourly-privacy-hidden" && (event.newValue === "0" || event.newValue === "1")) {
        try {
          if (!parsePrivacy(localStorage.getItem("hourly-privacy-v2"))) {
            fallbackNumbers = false; fallbackTime = false;
            privacyState = { numbers: event.newValue === "1", time: event.newValue === "1" };
          }
        } catch (_) { /* Keep the last safe state. */ }
      }
      applyPrivacy();
    }
  });
  window.addEventListener("hourly:privacy-change", event => {
    if (event.detail && typeof event.detail.numbersHidden === "boolean" && typeof event.detail.timeHidden === "boolean") {
      fallbackNumbers = false; fallbackTime = false;
      privacyState = { numbers: event.detail.numbersHidden, time: event.detail.timeHidden };
    }
    applyPrivacy();
  });
  window.addEventListener("hourly:language-change", () => { previous = ""; applyPrivacy(); });
  window.addEventListener("pageshow", applyPrivacy);
  applyPrivacy();
  setInterval(refresh, 3000);
})();
