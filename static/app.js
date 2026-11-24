"use strict";

(function () {
  // Compare the editable fields, including hidden drafts, without comparing
  // immediate actions such as login-at-startup or browser authorization.
  const settingsValueFields = ["annual_salary", "currency", "timezone", "provider", "service_id", "status_script_path", "night_pause_start", "night_pause_end", "theoretical_daily_hours", "screen_alert_hours"];
  const settingsCheckedFields = ["tracking_enabled", "pause_on_sleep", "night_pause_enabled", "screen_alert_enabled"];
  function supportedSettingsProvider(provider) {
    return ["disabled", "script", "verified_system", "system", "cisco"].includes(provider);
  }
  function captureSettingsDraft(form, salaryHistory) {
    const draft = {};
    settingsValueFields.forEach(function (key) { draft[key] = form.elements[key].value; });
    settingsCheckedFields.forEach(function (key) { draft[key] = form.elements[key].checked; });
    draft.workdays = Array.from(form.querySelectorAll('input[name="workday"]')).map(function (input) { return input.checked; });
    draft.salary_history = Array.from(salaryHistory.children).map(function (row) {
      return [row.querySelector(".salary-effective-date").value, row.querySelector(".salary-period-amount").value];
    });
    return draft;
  }
  function savedSettingsBaseline(previous, submitted, numbersHidden, timeHidden) {
    const baseline = Object.assign({}, submitted);
    if (numbersHidden) ["annual_salary", "currency", "salary_history"].forEach(function (key) { baseline[key] = previous[key]; });
    if (timeHidden) ["theoretical_daily_hours", "night_pause_start", "night_pause_end", "screen_alert_hours"].forEach(function (key) { baseline[key] = previous[key]; });
    return baseline;
  }
  if (typeof module === "object" && module.exports) {
    module.exports = { captureSettingsDraft: captureSettingsDraft, savedSettingsBaseline: savedSettingsBaseline, supportedSettingsProvider: supportedSettingsProvider };
    return;
  }
  const $ = function (id) { return document.getElementById(id); };
  const t = function (source, args) { return source == null ? source : window.hourlyI18n ? window.hourlyI18n.t(source, args) : source; };
  const locale = function () { return window.hourlyI18n && window.hourlyI18n.language() === "en" ? "en-US" : "zh-CN"; };
  const query = new URLSearchParams(window.location.search);
  const hash = new URLSearchParams(window.location.hash.slice(1));
  let pairToken = hash.get("pair") || "";
  let sessionToken = hash.get("access") || "";
  try {
    if (sessionToken) sessionStorage.setItem("hourly-access", sessionToken);
    else sessionToken = sessionStorage.getItem("hourly-access") || "";
  } catch (_) { /* A token from the launch URL remains usable without browser storage. */ }
  if (window.location.hash) history.replaceState(null, "", window.location.pathname + window.location.search);
  // A previously authorized browser can open a new tab using its HttpOnly cookie.
  let authBlocked = false;
  const browserAuthKey = "hourly-browser-auth-v1";
  let browserPairAttempted = false;
  function browserToken() {
    try {
      const saved = JSON.parse(localStorage.getItem(browserAuthKey) || "null");
      if (saved && typeof saved.token === "string" && Number.isFinite(saved.expires_at) && saved.expires_at * 1000 > Date.now()) return saved.token;
      if (saved) localStorage.removeItem(browserAuthKey);
    } catch (_) { /* Unavailable or invalid storage falls back to a normal session. */ }
    return "";
  }
  function authHeaders(extra) {
    const headers = Object.assign({ "X-Session-Token": sessionToken }, extra || {});
    const token = browserToken();
    if (token) headers["X-Browser-Token"] = token;
    return headers;
  }
  function updateBrowserAuthStatus() {
    const target = $("browser-auth-status");
    if (!target) return;
    const token = browserToken();
    const extend = $("extend-browser-auth");
    if (extend) extend.disabled = !token || authBlocked || mode === "demo";
    try {
      const saved = JSON.parse(localStorage.getItem(browserAuthKey) || "null");
      if (token && saved && Number.isFinite(saved.expires_at)) {
        target.textContent = t("当前浏览器有效期至 ") + new Date(saved.expires_at * 1000).toLocaleString(locale(), { hour12: false }) + t("。延长从现在起至少保留 14 天；不会影响后台计时。");
        return;
      }
    } catch (_) { /* Storage may be disabled by the browser. */ }
    target.textContent = t("此浏览器尚未记住或授权已过期；请通过本机启动入口重新打开。不会影响后台计时。");
  }
  async function rememberBrowser(csrf) {
    if (browserPairAttempted || !pairToken || mode === "demo") return;
    browserPairAttempted = true;
    try {
      const response = await fetch("/api/browser-auth/pair", { method: "POST", credentials: "same-origin", cache: "no-store", headers: authHeaders({ "Content-Type": "application/json", "X-CSRF-Token": csrf }), body: JSON.stringify({ pair_token: pairToken }) });
      if (!response.ok) return;
      const result = await response.json();
      if (typeof result.browser_token !== "string" || !Number.isFinite(result.expires_at)) return;
      localStorage.setItem(browserAuthKey, JSON.stringify({ token: result.browser_token, expires_at: result.expires_at }));
    } catch (_) { /* The current session remains usable when storage is unavailable. */ }
    finally { pairToken = ""; updateBrowserAuthStatus(); }
  }
  async function currentCsrf() {
    const response = await fetch("/api/session", { cache: "no-store", credentials: "same-origin", headers: authHeaders() });
    if (response.status === 401 || response.status === 403) { showAuthError(); throw new Error(t("本机授权已失效，请通过启动入口重新打开。")); }
    if (!response.ok) throw new Error(t("无法确认本机连接，请稍后重试。"));
    const session = await response.json();
    if (typeof session.csrf_token !== "string" || !session.csrf_token) throw new Error(t("本机连接信息不完整，请稍后重试。"));
    return session.csrf_token;
  }
  let vpnDetectionStatus = "idle";
  let vpnVerification = { service_id: "", verified: false, verified_states: [] };
  let verificationBusy = false;
  let cliCheckSequence = 0;
  let vpnDetectionSequence = 0;
  let settingsBaseline = null;
  let settingsSaving = false;
  let mode = query.get("demo") === "1" ? "demo" : "live";
  let period = ["today", "week", "month", "quarter", "half", "year", "rolling_year"].includes(query.get("period")) ? query.get("period") : "week";
  let data = null;
  let dashboardUnavailable = false;
  let selectedDate = null;
  let heatmapContext = "";
  let latestHeatmapDate = null;
  let heatmapView = "recent";
  let trendDays = [];
  let trendContext = "";
  let trendSelectedDate = null;
  let trendPlot = null;
  let trendScaleMode = "focus";
  let loadSequence = 0;
  let manualPauseBusy = false;
  let manualPauseStateUnknown = false;
  let autostartSequence = 0;
  const screenAlertsDeferred = new Set();
  let screenAlertRenderKey = "";
  let toastTimer;
  const isPrivate = function () { return !!(window.hourlyPrivacy && window.hourlyPrivacy.isHidden()); };
  const hideNumbers = function () { return !!(window.hourlyPrivacy && window.hourlyPrivacy.isNumbersHidden()); };
  const hideTime = function () { return !!(window.hourlyPrivacy && window.hourlyPrivacy.isTimeHidden()); };
  const MASKED = "***";
  const labels = { connected: "公司 VPN 已连接", disconnected: "公司 VPN 已断开", unknown: "连接状态未知", disabled: "尚未启用采集" };
  const money = function (value) { return value === null || value === undefined || !Number.isFinite(Number(value)) ? "—" : Number(value).toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
  const number = function (value, digits) { return value === null || value === undefined || !Number.isFinite(Number(value)) ? "—" : Number(value).toLocaleString(locale(), { maximumFractionDigits: digits === undefined ? 1 : digits }); };
  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function tz() { return data && data.settings && data.settings.timezone || "America/Los_Angeles"; }
  function formatTime(value, date) {
    if (!value) return "—";
    try {
      const opts = date ? { timeZone: tz(), month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false } : { timeZone: tz(), hour: "2-digit", minute: "2-digit", hour12: false };
      return new Intl.DateTimeFormat(locale(), opts).format(new Date(value));
    } catch (_) { return "—"; }
  }
  function formatDay(value) {
    if (!value) return "";
    try { return new Intl.DateTimeFormat(locale(), { timeZone: tz(), month: "2-digit", day: "2-digit" }).format(new Date(value)); }
    catch (_) { return ""; }
  }
  function duration(hours) {
    const value = Number(hours || 0);
    if (value > 0 && value * 60 < 1) return t("不足 1 分钟");
    const mins = Math.round(value * 60);
    if (mins < 60) return mins + t(" 分钟");
    return Math.floor(mins / 60) + t(" 小时") + (mins % 60 ? " " + mins % 60 + t(" 分钟") : "");
  }
  function toast(message) {
    $("toast").textContent = message;
    $("toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { $("toast").hidden = true; }, 3500);
  }
  function showAuthError() {
    authBlocked = true;
    $("error-banner").textContent = t("本机入口尚未授权或已经失效。请通过 start-hourly-rate.command 打开，或重新打开本机入口。");
    $("error-banner").hidden = false;
    $("date-range").textContent = t("等待本机入口授权");
    $("sync-now").disabled = true;
    $("manual-pause").disabled = true;
    updateTrackingControl();
    $("export-json").disabled = true;
    $("export-sqlite").disabled = true;
    $("export-csv").disabled = true;
    $("restore-json").disabled = true;
    $("open-manual").disabled = true;
  }
  function updateControls() {
    const collector = data && data.collector || {};
    const tracking = !!(data && data.settings && data.settings.tracking_enabled);
    const pauseButton = $("manual-pause");
    $("manual-pause-label").textContent = (manualPauseStateUnknown || dashboardUnavailable) ? t("计时状态未知") : collector.manual_paused ? t("恢复计时") : t("暂停计时");
    $("manual-pause-icon").textContent = collector.manual_paused ? "▶" : "Ⅱ";
    pauseButton.dataset.state = collector.manual_paused ? "paused" : "running";
    pauseButton.disabled = mode === "demo" || authBlocked || manualPauseBusy || manualPauseStateUnknown || dashboardUnavailable || !data || data.mode !== mode || (!tracking && !collector.manual_paused);
    pauseButton.title = mode === "demo" ? t("切换到本机记录后可暂停计时。") : (manualPauseStateUnknown || dashboardUnavailable) ? t("等待重新读取状态。") : collector.manual_paused ? (tracking ? t("恢复后仍按 VPN 状态和暂停规则计时。") : t("结束手动暂停；VPN 计时仍需在设置中开启。")) : !tracking ? t("请先在设置中启用 VPN 计时。") : t("暂停自动计时；VPN 连接状态仍会检测。");
    updateTrackingControl();
    $("open-manual").disabled = mode === "demo" || authBlocked;
    $("export-json").disabled = mode === "demo" || authBlocked;
    $("export-sqlite").disabled = mode === "demo" || authBlocked;
    $("export-csv").disabled = mode === "demo" || authBlocked;
    $("restore-json").disabled = mode === "demo" || authBlocked;
    $("open-settings").disabled = mode === "demo" || authBlocked || !data || data.mode !== mode;
    $("open-settings").title = mode === "demo" ? t("切换到本机记录后可查看和修改本机设置。") : "";
    $("open-manual").title = mode === "demo" ? t("切换到本机记录后可查看和修改工作历史。") : "";
    document.querySelectorAll("[data-mode]").forEach(function (button) {
      const active = button.dataset.mode === mode;
      button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll("[data-period]").forEach(function (button) {
      const active = button.dataset.period === period;
      button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active));
    });
    const params = new URLSearchParams();
    params.set("period", period);
    if (mode === "demo") params.set("demo", "1");
    if (isPrivate() && !window.hourlyPrivacy.canPersist()) params.set("privacy", window.hourlyPrivacy.fallbackValue());
    history.replaceState(null, "", "?" + params.toString());
  }
  function updateTrackingControl() {
    const collector = data && data.collector || {};
    const tracking = !!(data && data.settings && data.settings.tracking_enabled);
    let state, hint;
    if (authBlocked || manualPauseStateUnknown || dashboardUnavailable) {
      state = t("计时状态暂不可用"); hint = t("请重新连接本机服务后确认当前状态。");
    } else if (mode === "demo") {
      state = t("演示模式"); hint = t("切换到本机记录后，可在这里暂停或恢复计时。");
    } else if (!data || data.mode !== mode) {
      state = t("正在读取计时状态"); hint = t("暂停自动计时后，VPN 状态仍会继续检测。");
    } else if (collector.manual_paused) {
      state = t("已手动暂停"); hint = tracking ? t("将一直暂停，直到你手动恢复；VPN 状态仍会检测。") : t("手动暂停尚未结束；VPN 计时在设置中已关闭。");
    } else if (!tracking) {
      state = t("VPN 计时未开启"); hint = t("可在设置中选择 VPN 来源并开启计时。");
    } else if (collector.night_paused) {
      state = t("夜间自动暂停中"); hint = t("自动暂停结束后恢复；手动暂停会一直保持，直到你手动恢复。");
    } else if (collector.state === "connected") {
      state = t("正在记录工时"); hint = t("按 VPN 连接状态自动记录；需要休息时可以暂停。");
    } else if (collector.state === "disconnected") {
      state = t("VPN 未连接"); hint = t("当前不会自动记录工时；VPN 连接后会继续检测。");
    } else {
      state = t("VPN 状态未知"); hint = t("无法确认连接状态时不会推测工作时间。");
    }
    if ($("tracking-control-title").textContent !== state) $("tracking-control-title").textContent = state;
    if ($("tracking-control-hint").textContent !== hint) $("tracking-control-hint").textContent = hint;
    const donkey = $("work-donkey");
    const mood = state === t("正在记录工时") ? "work" : (state === t("已手动暂停") || state === t("夜间自动暂停中")) ? "rest" : "neutral";
    donkey.dataset.mood = mood;
    donkey.dataset.active = mood === "work" ? "true" : "false";
  }
  async function load() {
    const requestSequence = ++loadSequence;
    updateControls();
    try {
      const response = await fetch("/api/dashboard?period=" + encodeURIComponent(period) + "&demo=" + (mode === "demo" ? "1" : "0"), { cache: "no-store", credentials: "same-origin", headers: authHeaders() });
      if (response.status === 401 || response.status === 403) { showAuthError(); return false; }
      if (!response.ok) throw new Error(t("暂时无法读取本机记录。请确认本机服务仍在运行。"));
      const received = await response.json();
      if (requestSequence !== loadSequence) return false;
      data = received;
      authBlocked = false;
      manualPauseStateUnknown = false;
      dashboardUnavailable = false;
      $("error-banner").hidden = true;
      updateControls();
      render();
      await rememberBrowser(received.csrf_token);
      return true;
    } catch (error) {
      if (requestSequence !== loadSequence) return false;
      dashboardUnavailable = true;
      $("error-banner").textContent = t(error.message) || t("读取失败，请稍后重试。");
      $("error-banner").hidden = false;
      updateControls();
      return false;
    }
  }
  function renderNotice() {
    const notice = $("notice");
    notice.replaceChildren();
    if (mode === "demo") {
      notice.append(document.createTextNode(t("演示预览 · 使用独立的示例薪资与模拟记录。这里的数字不是你的真实收入或工作时间；不会写入本机记录。")));
      notice.hidden = false;
    } else if (data.summary.salary_incomplete || data.summary.current_annual_salary === null) {
      notice.append(document.createTextNode(data.summary.salary_incomplete ? t("所选时段中有已记录的日期缺少薪资。补齐初始年薪或相应生效日期后，就能重新计算实际时薪。") : t("当前日期还没有生效的薪资。设置初始年薪或添加生效日期，就能建立理论时薪基准。")));
      const button = element("button", "", t("打开本机设置")); button.type = "button"; button.addEventListener("click", openSettings); notice.append(button);
      notice.hidden = false;
    } else if (!data.settings.tracking_enabled) {
      notice.append(document.createTextNode(t("真实采集尚未开启。确认公司 VPN 类型与设备使用规定后，可在设置中启用；缺少记录的时段会保持未知。")));
      notice.hidden = false;
    } else { notice.hidden = true; }
  }
  function screenAlertDate(value) {
    const instant = new Date(value);
    if (!Number.isFinite(instant.getTime())) return "";
    try {
      const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz(), year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(instant);
      const part = function (kind) { const found = parts.find(function (item) { return item.type === kind; }); return found ? found.value : ""; };
      const result = part("year") + "-" + part("month") + "-" + part("day");
      return /^\d{4}-\d{2}-\d{2}$/.test(result) ? result : "";
    } catch (_) { return ""; }
  }
  function screenAlertTime(value) {
    const instant = new Date(value);
    if (!Number.isFinite(instant.getTime())) return "—";
    try { return new Intl.DateTimeFormat(locale(), { timeZone: tz(), year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(instant); }
    catch (_) { return "—"; }
  }
  function renderScreenAlerts() {
    const panel = $("screen-alert-panel"), list = $("screen-alert-list");
    const items = mode === "live" && data && data.mode === "live" && Array.isArray(data.screen_alerts)
      ? data.screen_alerts.filter(function (item) { return item && item.status === "pending" && !screenAlertsDeferred.has(String(item.id)); }) : [];
    const key = JSON.stringify([hideTime(), items.map(function (item) { return [item.id, screenAlertTime(item.start), screenAlertTime(item.end), item.active]; })]);
    panel.hidden = items.length === 0;
    if (key === screenAlertRenderKey) return;
    screenAlertRenderKey = key;
    list.replaceChildren();
    items.forEach(function (item) {
      const row = element("article", "screen-alert-item");
      const startDate = screenAlertDate(item.start), endDate = screenAlertDate(item.end);
      row.append(element("strong", "screen-alert-range", (hideTime() ? MASKED : screenAlertTime(item.start) + " — " + screenAlertTime(item.end)) + (item.active ? t(" · 仍在记录") : "")));
      const detail = item.active ? t("此段仍在自动记录，可先暂停或等结束后再确认；也可以先打开工作历史查看。") : t("请核对这段时间；原始 VPN 记录保留，确认处理完成仅标记提醒已处理，不修改工时。");
      row.append(element("p", "screen-alert-note", detail + (startDate && endDate && startDate !== endDate ? t(" 此时段跨日期，请在工作历史分别核对相关日期。") : "")));
      const actions = element("div", "screen-alert-actions");
      const keep = element("button", "secondary-button", t("确认处理完成")); keep.type = "button"; keep.disabled = Boolean(item.active);
      keep.title = t("仅标记为已确认，不修改工时。");
      if (item.active) keep.title = t("此时段仍在记录，请先暂停或等它结束后再确认。");
      keep.addEventListener("click", async function () {
        if (authBlocked || mode !== "live" || item.active) return;
        keep.disabled = true;
        try {
          await post("/api/screen-alert/keep", { id: item.id });
          screenAlertsDeferred.add(String(item.id));
          screenAlertRenderKey = "";
          renderScreenAlerts();
          toast(t("已确认，工时没有改变"));
          await load();
        } catch (error) { toast(t(error.message) || t("确认失败，请稍后重试")); keep.disabled = false; }
      });
      const edit = element("button", "secondary-button", t("去工作历史修正/排除")); edit.type = "button"; edit.disabled = !startDate;
      edit.addEventListener("click", function () { if (mode === "live" && !authBlocked && startDate) window.dispatchEvent(new CustomEvent("hourly:open-history", { detail: { date: startDate } })); });
      const later = element("button", "secondary-button", t("稍后处理")); later.type = "button";
      later.addEventListener("click", function () { screenAlertsDeferred.add(String(item.id)); screenAlertRenderKey = ""; renderScreenAlerts(); toast(t("已暂时收起，重新打开页面后仍可处理")); });
      actions.append(keep, edit, later); row.append(actions); list.append(row);
    });
  }
  function renderPeriodComparison(summary, currency) {
    const node = $("period-comparison"), comparison = summary.period_comparison;
    const titleNode = $("period-comparison-title"), changeNode = $("period-comparison-change");
    const priorNode = $("period-comparison-prior"), detailNode = $("period-comparison-detail");
    const setText = function (target, value) { if (target.textContent !== value) target.textContent = value; };
    node.dataset.direction = "neutral";
    if (!comparison) {
      setText(titleNode, t("与上期相比"));
      setText(changeNode, "—");
      setText(priorNode, t("上期对比暂不可用"));
      setText(detailNode, ["today", "week", "month"].includes(period) ? t("请重新打开应用后重试。") : t("选择今天、本周或本月，可查看对应的上期对比。") );
      return;
    }
    const rawLabel = comparison.label || "上期", label = t(rawLabel);
    setText(titleNode, rawLabel === "上一个工作日" ? t("与上个工作日相比") : t("与") + label + t("相比"));
    let range = t("完整周期");
    if (/^\d{4}-\d{2}-\d{2}$/.test(comparison.start || "") && /^\d{4}-\d{2}-\d{2}$/.test(comparison.end_exclusive || "")) {
      const lastDay = new Date(Date.parse(comparison.end_exclusive + "T00:00:00Z") - 86400000);
      if (Number.isFinite(lastDay.getTime())) {
        const end = lastDay.toISOString().slice(0, 10);
        range = comparison.start === end ? comparison.start : comparison.start + " — " + end;
      }
    }
    const timeframe = t("本期截至现在 · ") + label + "：" + range + t("（完整周期）");
    if (hideNumbers()) {
      setText(changeNode, MASKED);
      setText(priorNode, label + t("时薪：") + MASKED);
      setText(detailNode, timeframe);
      return;
    }
    const previous = comparison.actual_rate;
    if (previous === null || previous === undefined || !Number.isFinite(Number(previous))) {
      const reason = comparison.rate_status === "missing_salary" ? t("缺少薪资") : comparison.rate_status === "no_work" ? t("没有工时") : t("没有可用记录");
      setText(changeNode, "—");
      setText(priorNode, label + t("时薪：—（") + reason + "）");
      setText(detailNode, timeframe + t("；暂无可比时薪。"));
      return;
    }
    setText(priorNode, label + t("时薪：") + currency + money(previous) + t("/小时") + (comparison.rate_floor_applied && !hideTime() ? t("（工时不足 1 小时，按 1 小时估算）") : ""));
    if (summary.actual_rate === null || summary.actual_rate === undefined || !Number.isFinite(Number(summary.actual_rate))) {
      setText(changeNode, "—");
      setText(detailNode, timeframe + t("；本期暂无可比时薪。"));
    } else if (Number(previous) === 0) {
      setText(changeNode, "—");
      setText(detailNode, timeframe + t("；上期为 0，无法计算百分比。"));
    } else if (comparison.delta_percent === null || comparison.delta_percent === undefined || !Number.isFinite(Number(comparison.delta_percent))) {
      setText(changeNode, "—");
      setText(detailNode, timeframe + t("；暂无可比变化。"));
    } else {
      const delta = Number(comparison.delta_percent);
      node.dataset.direction = Math.abs(delta) < 0.05 ? "neutral" : delta > 0 ? "up" : "down";
      setText(changeNode, Math.abs(delta) < 0.05 ? t("基本持平") : (delta > 0 ? t("↑ 高 ") : t("↓ 低 ")) + number(Math.abs(delta)) + "%");
      setText(detailNode, timeframe);
    }
  }
  function render() {
    const s = data.summary;
    const currency = { USD: "$", CNY: "¥", EUR: "€", GBP: "£", CAD: "C$", JPY: "¥" }[data.settings.currency] || data.settings.currency;
    $("actual-currency").textContent = currency;
    $("theory-currency").textContent = currency;
    $("actual-currency").title = data.settings.currency;
    $("theory-currency").title = data.settings.currency;
    $("actual-rate").textContent = hideNumbers() ? MASKED : money(s.actual_rate);
    $("theory-rate").textContent = hideNumbers() ? MASKED : money(s.theoretical_rate);
    const workHours = Number(s.work_hours);
    const shortWork = Number.isFinite(workHours) && workHours > 0 && workHours < 0.1;
    $("work-hours").textContent = hideTime() ? MASKED : shortWork ? (workHours * 60 < 1 ? "<1" : t("约 ") + number(workHours * 60, 0)) : number(s.work_hours);
    $("work-hours-unit").textContent = !hideTime() && shortWork ? t("分钟") : t("小时");
    $("recorded-days").textContent = hideTime() ? MASKED : number(s.recorded_days, 0) + t(" 天");
    $("date-range").textContent = formatDay(s.start) + " — " + formatDay(s.end) + t(" · 截至现在");
    const rateChange = $("rate-change");
    rateChange.classList.remove("positive");
    if (hideNumbers()) {
      rateChange.textContent = MASKED;
    } else if (s.actual_rate === null || s.actual_rate === undefined) {
      rateChange.textContent = s.salary_incomplete ? t("待补齐时段薪资") : hideTime() ? t("等待时薪数据") : Number(s.work_hours) > 0 ? t("等待薪资设置") : t("尚无可计算工时");
    } else if (s.delta_percent === null || s.delta_percent === undefined) {
      rateChange.textContent = t("固定日薪口径");
    } else if (Math.abs(s.delta_percent) < 0.05) {
      rateChange.textContent = t("基本持平");
    } else {
      const positive = s.delta_percent > 0;
      rateChange.textContent = (positive ? t("↑ 高 ") : t("↓ 低 ")) + number(Math.abs(s.delta_percent)) + "%";
      rateChange.classList.toggle("positive", positive);
    }
    $("actual-note").textContent = s.rate_floor_applied && !hideTime() ? t("固定日薪 ÷ 1 小时") : t("所选时段收入 ÷ 总工时");
    const manualDays = Number(s.manual_days || 0);
    const estimatedHours = Number(s.estimated_hours || 0);
    const sleepEstimatedHours = Number(s.sleep_estimated_hours || 0);
    $("actual-source").textContent = manualDays > 0 ? t("含手动记录") : sleepEstimatedHours > 0 ? t("含睡眠估算") : t("VPN 口径");
    $("actual-estimate-note").textContent = isPrivate() ? t("具体数字已隐藏；记录与计算不受影响。") : (s.rate_floor_applied ? t("工时不足 1 小时，时薪按 1 小时估算；真实工时保持不变。") : "") + t("按整日收入估算，今日随工时更新，缺失记录可能偏高。") + (manualDays > 0 ? t(" 含 ") + number(manualDays, 0) + t(" 天手动记录") + (estimatedHours > 0 ? t("，其中 ") + number(estimatedHours) + t(" 小时为人工估算") : "") + "。" : "") + (sleepEstimatedHours > 0 ? t(" 含睡眠估算 ") + number(sleepEstimatedHours, 2) + t(" 小时。") : "");
    $("actual-estimate-note").hidden = Number(s.work_hours) <= 0 && manualDays <= 0;
    $("theory-note").textContent = t("当前生效年薪 ÷ 本年理论工时");
    renderPeriodComparison(s, currency);
    renderNotice();
    renderScreenAlerts();
    renderDailyTrend(s.period_days || []);
    renderHeatmap(heatmapDays());
    renderTimeline(s.timeline || []);
    renderCollector();
    if (isPrivate()) document.documentElement.dataset.privacyReady = "true";
  }
  function level(hours) {
    return window.HourlyHistoryCalendar.level(hours);
  }
  function dayDescription(day) {
    const date = day.date.replaceAll("-", "/");
    if (day.status === "future") return date + t(" · 尚未发生");
    if (day.status === "unknown" && !day.manual_kind && !(Number(day.sleep_estimated_hours) > 0)) return date + t(" · 缺少记录，无法判断是否工作");
    const currency = data.settings.currency;
    const source = day.source === "manual_estimate" ? t("手动估算工时") : day.source === "manual" ? t("工时（含手动记录）") : Number(day.sleep_estimated_hours) > 0 ? t("合计工时") : t("VPN 工时");
    return date + " · " + source + " " + (hideTime() ? MASKED : duration(day.work_hours))
      + t(" · 收入 ") + (hideNumbers() ? MASKED : money(day.income)) + " " + currency
      + t(" · 实际时薪 ") + (hideNumbers() ? MASKED : money(day.actual_rate)) + " " + currency + t("/小时")
      + (day.rate_floor_applied && !hideTime() ? t(" · 工时不足 1 小时，时薪按 1 小时估算") : "")
      + (day.manual_kind ? t(" · 原始 VPN 记录 ") + (hideTime() ? MASKED : duration(day.vpn_work_hours)) : "")
      + (Number(day.sleep_estimated_hours) > 0 ? t(" · 含睡眠估算 ") + (hideTime() ? MASKED : number(day.sleep_estimated_hours, 2) + t(" 小时")) : "")
      + (day.source === "manual_estimate" ? t(" · 按当天总时长估算，无具体时间片段") : day.status === "partial" ? t(" · 全天记录不完整，时薪可能偏高") : "")
      + (day.manual_note && !isPrivate() ? t(" · 备注：") + day.manual_note : "");
  }
  function trendHasRecord(day) {
    return day.status !== "future" && (day.status !== "unknown" || !!day.manual_kind || Number(day.sleep_estimated_hours) > 0);
  }
  function trendValue(day, field) {
    const value = day[field];
    return trendHasRecord(day) && value !== null && value !== undefined && Number.isFinite(Number(value)) ? Number(value) : null;
  }
  function svgElement(tag, attributes, text) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attributes || {}).forEach(function (entry) { node.setAttribute(entry[0], entry[1]); });
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function trendScale(values, kind) {
    const known = values.filter(function (value) { return value !== null && Number.isFinite(value); });
    const peak = known.length ? Math.max(...known) : 0;
    const low = known.length ? Math.min(...known) : 0;
    const minimumSpan = kind === "hours" ? 2 : Math.max(10, peak * 0.1);
    const span = Math.max(peak - low, minimumSpan);
    let lower = trendScaleMode === "zero" ? 0 : Math.max(0, low - Math.max((span - (peak - low)) / 2, span * 0.12));
    let upper = Math.min(Number.MAX_VALUE, peak + Math.max((span - (peak - low)) / 2, span * 0.12));
    if (!known.length) { lower = 0; upper = kind === "hours" ? 8 : 100; }
    if (!(upper > lower)) { lower = 0; upper = peak || minimumSpan; }
    const rough = (upper - lower) / 4;
    const power = Math.pow(10, Math.floor(Math.log10(rough)));
    const unit = rough / power;
    const step = (unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 2.5 ? 2.5 : unit <= 5 ? 5 : 10) * power;
    const min = Math.max(0, Math.floor(lower / step) * step);
    const roundedMax = Math.ceil(upper / step) * step;
    const max = Number.isFinite(roundedMax) ? roundedMax : upper;
    const ticks = [];
    for (let i = 0; i < 12; i++) {
      const value = min + i * step;
      if (!Number.isFinite(value) || value > max + step * 1e-9) break;
      ticks.push(value);
    }
    if (!ticks.length || max - ticks[ticks.length - 1] > step * 0.01) ticks.push(max);
    return { min: min, max: max, ticks: ticks };
  }
  function renderDailyTrend(days) {
    trendDays = days;
    const context = mode + ":" + period + ":" + (days[0] && days[0].date || "");
    if (context !== trendContext || !days.some(function (day) { return day.date === trendSelectedDate; })) {
      const recorded = days.filter(trendHasRecord);
      const selected = recorded[recorded.length - 1] || days[days.length - 1];
      trendSelectedDate = selected ? selected.date : null;
    }
    trendContext = context;
    $("trend-period").textContent = t(data.summary.label || "所选时段");
    const slider = $("trend-date");
    slider.max = String(Math.max(0, days.length - 1));
    slider.disabled = days.length <= 1;
    drawDailyTrend();
  }
  function drawDailyTrend() {
    const svg = $("daily-trend");
    svg.replaceChildren();
    trendPlot = null;
    if (!trendDays.length) {
      $("trend-empty").hidden = false;
      $("trend-selected-date").textContent = "—";
      $("trend-hours").textContent = "—";
      $("trend-rate").textContent = "—";
      $("trend-day-note").textContent = t("这个时段还没有每日记录。");
      return;
    }
    const width = Math.max(260, $("trend-chart").clientWidth);
    const left = width < 420 ? 53 : 64;
    const right = width - 15;
    const height = 324;
    const currency = data.settings.currency;
    const hours = trendDays.map(function (day) { return trendValue(day, "work_hours"); });
    const rates = trendDays.map(function (day) { return trendValue(day, "actual_rate"); });
    const x = function (i) { return trendDays.length === 1 ? (left + right) / 2 : left + i * (right - left) / (trendDays.length - 1); };
    const series = [{ values: hours, top: 29, bottom: 130, scale: trendScale(hours, "hours"), className: "trend-work", label: t("工作时长 · 小时") },
      { values: rates, top: 190, bottom: 291, scale: trendScale(rates, "rate"), className: "trend-pay", label: t("实际时薪 · ") + currency + t("/小时") }];
    const cropped = series.some(function (item) { return item.scale.min > 0; });
    $("trend-scale-note").textContent = trendScaleMode === "zero" ? t("纵轴从 0 开始，便于比较绝对大小。")
      : cropped ? t("纵轴已聚焦数值范围，部分起点不为 0；请结合刻度判断变化。") : t("纵轴按记录自动调整，保留真实零值。");
    if (isPrivate()) $("trend-scale-note").textContent = t("所选数值已隐藏，曲线仍显示变化趋势。");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.append(svgElement("desc", { id: "trend-chart-description" }, t("所选时段 ") + trendDays[0].date + t(" 至 ") + trendDays[trendDays.length - 1].date + t("，上图为每日工作小时，下图为实际时薪。缺少记录处断线。") + (isPrivate() ? t("所选数值已隐藏。") : t("使用下方日期滑块查看准确数值。"))));
    series.forEach(function (item) {
      const seriesHidden = item.className === "trend-work" ? hideTime() : hideNumbers();
      const y = function (value) { return item.bottom - (value - item.scale.min) / (item.scale.max - item.scale.min) * (item.bottom - item.top); };
      item.y = y;
      svg.append(svgElement("text", { x: left, y: item.top - 13, class: "trend-axis-title " + item.className }, item.label + (item.scale.min > 0 ? t(" · 非零起点") : "")));
      item.scale.ticks.forEach(function (value) {
        const ordinate = y(value);
        svg.append(svgElement("line", { x1: left, x2: right, y1: ordinate, y2: ordinate, class: "trend-grid" }));
        if (!seriesHidden) svg.append(svgElement("text", { x: left - 10, y: ordinate + 3, "text-anchor": "end", class: "trend-axis " + (item.className === "trend-work" ? "trend-axis-hours" : "trend-axis-rate") }, compactAxis(value)));
      });
      let path = "";
      let previous = false;
      item.values.forEach(function (value, index) {
        if (value === null) { previous = false; return; }
        path += (previous ? " L " : " M ") + x(index) + " " + y(value);
        previous = true;
      });
      svg.append(svgElement("path", { d: path, class: "trend-line " + item.className }));
      item.values.forEach(function (value, index) {
        if (value === null) return;
        const dot = svgElement("circle", { cx: x(index), cy: y(value), r: trendDays.length > 90 ? 2 : 3, class: "trend-point " + item.className });
        dot.append(svgElement("title", {}, trendDays[index].date + " · " + (seriesHidden ? MASKED : item.className === "trend-work" ? number(value, 2) + t(" 小时") : money(value) + " " + currency + t("/小时"))));
        svg.append(dot);
      });
      if (item.values.every(function (value) { return value === null; })) {
        svg.append(svgElement("text", { x: (left + right) / 2, y: (item.top + item.bottom) / 2, "text-anchor": "middle", class: "trend-no-values" }, item.className === "trend-work" ? t("暂无工时记录") : t("暂无可计算的时薪")));
      }
    });
    const tickCount = Math.min(trendDays.length, width < 420 ? 3 : width < 720 ? 5 : 7);
    for (let tick = 0; tick < tickCount; tick++) {
      const index = tickCount === 1 ? 0 : Math.round(tick * (trendDays.length - 1) / (tickCount - 1));
      const day = trendDays[index].date;
      const crossYear = trendDays[0].date.slice(0, 4) !== trendDays[trendDays.length - 1].date.slice(0, 4);
      const label = crossYear ? day.slice(2).replaceAll("-", "/") : Number(day.slice(5, 7)) + "/" + Number(day.slice(8));
      svg.append(svgElement("text", { x: x(index), y: 316, "text-anchor": tickCount === 1 ? "middle" : tick === 0 ? "start" : tick === tickCount - 1 ? "end" : "middle", class: "trend-axis" }, label));
    }
    const selection = svgElement("g", { class: "trend-selection", "aria-hidden": "true" });
    svg.append(selection);
    trendPlot = { width: width, left: left, right: right, x: x, series: series, selection: selection };
    $("trend-empty").hidden = hours.some(function (value) { return value !== null; });
    selectTrendDate(Math.max(0, trendDays.findIndex(function (day) { return day.date === trendSelectedDate; })));
  }
  function compactAxis(value) {
    if (value >= 1000000000000) return value.toExponential(1);
    if (value >= 1000000000) return number(value / 1000000000, 1) + "b";
    if (value >= 1000000) return number(value / 1000000, 1) + "m";
    if (value >= 1000) return number(value / 1000, 1) + "k";
    if (value > 0 && value < 0.01) return number(value, 6);
    return number(value, 2);
  }
  function selectTrendDate(index) {
    const day = trendDays[index];
    if (!day || !trendPlot) return;
    trendSelectedDate = day.date;
    const hours = trendValue(day, "work_hours");
    const rate = trendValue(day, "actual_rate");
    const slider = $("trend-date");
    slider.value = String(index);
    $("trend-selected-date").textContent = day.date.replaceAll("-", "/");
    $("trend-hours").textContent = hideTime() ? MASKED : hours === null ? t("未知") : hours > 0 && hours < 0.1 ? duration(hours) : number(hours, 2) + t(" 小时");
    $("trend-rate").textContent = hideNumbers() ? MASKED : rate === null ? "—" : money(rate) + " " + data.settings.currency + t("/小时");
    slider.setAttribute("aria-valuetext", day.date + t("，工时 ") + $("trend-hours").textContent + t("，实际时薪 ") + $("trend-rate").textContent);
    const notes = [];
    if (hours === null) notes.push(t("缺少记录，不按零工时处理"));
    else {
      if (day.manual_kind === "daily_total") notes.push(t("手动估算的每日总工时"));
      else if (day.manual_kind === "intervals_override") notes.push(t("按手动修正的时段计算，原始 VPN 记录保留"));
      else if (day.manual_kind) notes.push(t("含手动记录，与 VPN 记录重叠的部分只计一次"));
      else if (Number(day.sleep_estimated_hours) <= 0) notes.push(t("来自 VPN 连接记录"));
      if (Number(day.sleep_estimated_hours) > 0) notes.push(hideTime() ? t("含睡眠估算") : t("含睡眠估算 ") + number(day.sleep_estimated_hours, 2) + t(" 小时"));
      if (day.partial_day && day.date !== data.summary.end.slice(0, 10)) notes.push(t("仅统计所选范围内的时段"));
      if (day.status === "partial" && day.manual_kind !== "daily_total") notes.push(t("当天记录不完整"));
      if (rate === null) notes.push(day.rate_status === "missing_salary" ? t("缺少当天薪资，暂不计算时薪") : hideTime() ? t("暂不计算时薪") : t("零工时，暂不计算时薪"));
      if (day.rate_floor_applied && !hideTime()) notes.push(t("工时不足 1 小时，时薪按 1 小时估算"));
      if (day.date === data.summary.end.slice(0, 10)) notes.push(t("今日截至现在"));
      if (day.manual_note && !isPrivate()) notes.push(day.manual_note);
    }
    $("trend-day-note").textContent = notes.join(" · ");
    const guide = trendPlot.selection;
    guide.replaceChildren();
    const selectedX = trendPlot.x(index);
    guide.append(svgElement("line", { x1: selectedX, x2: selectedX, y1: 27, y2: 293, class: "trend-guide" }));
    trendPlot.series.forEach(function (item) {
      const value = item.values[index];
      if (value !== null) guide.append(svgElement("circle", { cx: selectedX, cy: item.y(value), r: 5, class: "trend-selected-point " + item.className }));
    });
  }
  function selectTrendPointer(event) {
    if (!trendPlot || (event.type === "pointermove" && event.pointerType !== "mouse")) return;
    const rect = $("daily-trend").getBoundingClientRect();
    const position = (event.clientX - rect.left) / rect.width * trendPlot.width;
    const index = trendDays.length === 1 ? 0 : Math.max(0, Math.min(trendDays.length - 1, Math.round((position - trendPlot.left) / (trendPlot.right - trendPlot.left) * (trendDays.length - 1))));
    if (trendDays[index].date !== trendSelectedDate) selectTrendDate(index);
  }
  function heatmapDays() {
    if (!data) return [];
    return heatmapView === "recent" && Array.isArray(data.summary.heatmap_recent_days)
      ? data.summary.heatmap_recent_days : data.summary.days || [];
  }
  function renderHeatmap(days) {
    const grid = $("heatmap"); const months = $("heatmap-months");
    const scroll = $("heatmap-scroll");
    const previousScroll = scroll.scrollLeft;
    grid.replaceChildren(); months.replaceChildren();
    if (!days.length) {
      $("heatmap-year").textContent = "";
      $("locate-latest-record").disabled = true;
      $("heatmap-scroll-hint").hidden = true;
      latestHeatmapDate = null;
      return;
    }
    const year = days[0].date.slice(0, 4);
    const context = mode + ":" + heatmapView + ":" + days[0].date;
    const initialPosition = heatmapContext !== context;
    if (initialPosition && !days.some(function (day) { return day.date === selectedDate; })) selectedDate = null;
    heatmapContext = context;
    const recorded = days.filter(function (day) { return day.status !== "future" && (day.manual_kind || (day.status !== "unknown" && day.status)); });
    const elapsed = days.filter(function (day) { return day.status !== "future"; });
    latestHeatmapDate = (recorded[recorded.length - 1] || elapsed[elapsed.length - 1] || days[0]).date;
    $("locate-latest-record").disabled = false;
    $("heatmap-year").textContent = heatmapView === "year" ? year : t("最近半年");
    $("heatmap-range").textContent = days[0].date.replaceAll("-", "/") + " — " + days[days.length - 1].date.replaceAll("-", "/");
    scroll.classList.toggle("heatmap-recent", heatmapView === "recent");
    $("heatmap").setAttribute("aria-label", heatmapView === "recent" ? t("今天前后三个月的工作时间，点击日期查看详情") : t("全年工作时间，点击日期查看详情"));
    const firstDay = new Date(days[0].date + "T12:00:00Z");
    const offset = (firstDay.getUTCDay() + 6) % 7;
    const columns = Math.ceil((offset + days.length) / 7);
    scroll.style.setProperty("--heatmap-columns", String(columns));
    grid.style.gridTemplateColumns = "repeat(" + columns + ", minmax(9px, 1fr))";
    months.style.gridTemplateColumns = "repeat(" + columns + ", minmax(9px, 1fr))";
    const monthCols = new Map();
    days.forEach(function (day, i) {
      if (day.date.endsWith("-01") || i === 0) {
        const month = locale() === "en-US" ? new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" }).format(new Date(day.date + "T12:00:00Z")) : Number(day.date.slice(5, 7)) + " 月";
        monthCols.set(Math.floor((offset + i) / 7), (day.date.endsWith("-01-01") ? day.date.slice(0, 4) + " " : "") + month);
      }
    });
    for (let col = 0; col < columns; col++) months.append(element("span", "", monthCols.get(col) || ""));
    for (let pad = 0; pad < offset; pad++) grid.append(element("span", "day-cell padding"));
    days.forEach(function (day) {
      const button = element("button", "day-cell");
      button.type = "button";
      button.dataset.date = day.date;
      if (day.status === "unknown" || day.status === "future") button.classList.add(day.status);
      else { button.classList.add("level-" + level(day.work_hours)); if (day.status === "partial") button.classList.add("partial"); }
      button.classList.toggle("selected", selectedDate === day.date);
      const isToday = day.date === data.summary.end.slice(0, 10);
      button.classList.toggle("today", isToday);
      if (isToday) button.setAttribute("aria-current", "date");
      const description = dayDescription(day);
      button.setAttribute("aria-label", description); button.title = description;
      button.addEventListener("click", function () {
        selectedDate = day.date;
        grid.querySelectorAll(".selected").forEach(function (el) { el.classList.remove("selected"); });
        button.classList.add("selected");
        $("day-detail").textContent = description;
      });
      grid.append(button);
    });
    for (let pad = offset + days.length; pad < columns * 7; pad++) grid.append(element("span", "day-cell padding"));
    if (selectedDate) {
      const selected = days.find(function (d) { return d.date === selectedDate; });
      if (selected) $("day-detail").textContent = dayDescription(selected);
    }
    if (initialPosition) {
      if (selectedDate) positionHeatmapDate(selectedDate);
      else locateLatestRecord();
    }
    else scroll.scrollLeft = previousScroll;
    updateHeatmapOverflow();
  }
  function locateLatestRecord() {
    if (!latestHeatmapDate) return;
    const button = $("heatmap").querySelector('[data-date="' + latestHeatmapDate + '"]');
    if (!button) return;
    button.click();
    positionHeatmapDate(latestHeatmapDate);
  }
  function positionHeatmapDate(date) {
    const button = $("heatmap").querySelector('[data-date="' + date + '"]');
    if (!button) return;
    const scroll = $("heatmap-scroll");
    const cellRect = button.getBoundingClientRect();
    const scrollRect = scroll.getBoundingClientRect();
    // Change this panel's horizontal offset without moving the page vertically.
    scroll.scrollLeft += cellRect.left - scrollRect.left - (scroll.clientWidth - cellRect.width) / 2;
  }
  function updateHeatmapOverflow() {
    const scroll = $("heatmap-scroll");
    $("heatmap-scroll-hint").hidden = !latestHeatmapDate || scroll.scrollWidth <= scroll.clientWidth + 1;
    $("heatmap-scroll-hint").textContent = heatmapView === "recent" ? t("↔ 左右滑动查看前后三个月") : t("↔ 左右滑动查看全年");
  }
  function renderTimeline(intervals) {
    const container = $("timeline"); container.replaceChildren();
    const recent = intervals.slice(-6).reverse();
    if (!recent.length) {
      const empty = element("div", "timeline-empty");
      empty.append(element("div", "empty-icon", "—"), element("strong", "", t("还没有工作片段")), element("p", "", t("开启采集并完成一次同步后，连接与断开的时间会出现在这里。")));
      container.append(empty); return;
    }
    recent.forEach(function (interval) {
      const row = element("div", "timeline-entry " + interval.state + (interval.source === "manual" || interval.source === "manual_override" ? " manual-source" : interval.source === "sleep_estimate" ? " sleep-estimate-source" : ""));
      const date = element("span", "timeline-date", formatDay(interval.start));
      const marker = element("span", "timeline-marker"); marker.setAttribute("aria-hidden", "true");
      const detail = element("div", "timeline-detail");
      const sourceLabels = { manual: t("手动记录的工作时段"), manual_paused: t("手动暂停 · 未计入工时"), night_paused: t("夜间暂停 · 未计入工时"), sleep_estimate: t("睡眠期间估算工时"), sleep_paused: t("系统睡眠 · 已暂停计时"), sleep_unknown: t("系统睡眠 · 无法估算工时") };
      const title = interval.source === "manual_override" ? (interval.state === "connected" ? t("手动修正 · 已计入") : t("手动修正 · 未计入")) : sourceLabels[interval.source] || t(labels[interval.state] || "未知时段");
      detail.append(element("div", "timeline-title", title));
      const spansDay = formatDay(interval.start) !== formatDay(interval.end);
      detail.append(element("div", "timeline-time", hideTime() ? MASKED : formatTime(interval.start) + " — " + formatTime(interval.end, spansDay)));
      const elapsed = (new Date(interval.end) - new Date(interval.start)) / 3600000;
      row.append(date, marker, detail, element("span", "timeline-duration", hideTime() ? MASKED : duration(elapsed)));
      container.append(row);
    });
  }
  function renderCollector() {
    const c = data.collector || {};
    $("collector-state").textContent = t(labels[c.state] || "连接状态未知");
    $("collector-dot").className = "status-dot " + (c.state === "connected" ? "connected" : c.state === "unknown" ? "unknown" : "muted");
    $("collector-message").textContent = t(c.message || "采集状态暂不可用。");
    if (c.manual_paused) {
      $("collector-state").textContent += t(" · 已手动暂停");
      $("collector-message").textContent += t("；手动暂停期间不计入自动工时，点击“恢复计时”后才继续。");
    }
    if (c.night_paused && data.settings && data.settings.tracking_enabled) {
      $("collector-state").textContent += t(" · 夜间暂停计时");
      $("collector-message").textContent += t("；夜间自动暂停，结束后恢复计入工时。");
    }
    $("last-sync").textContent = hideTime() ? MASKED : formatTime(c.last_synced_at, true);
    $("pending-count").textContent = hideTime() ? MASKED : number(c.pending_count || 0, 0) + t(" 条");
    $("storage-path").textContent = data.privacy && data.privacy.storage_path || t("本机数据目录");
    $("sync-now").disabled = mode === "demo";
    $("sync-now").title = mode === "demo" ? t("演示记录无需同步；切换到本机记录可同步真实数据。") : "";
    renderPowerStatus();
  }
  function renderPowerStatus() {
    const monitor = data.power_monitor || (data.collector || {}).power_monitor || {};
    const available = monitor.available === true;
    const message = t(monitor.message || (available ? "系统睡眠识别已就绪。" : "暂时无法识别系统睡眠，不能准确应用睡眠计时设置。"));
    $("sleep-monitor-status").textContent = message;
    $("sleep-monitor-status").classList.toggle("unavailable", !available);
    $("sleep-monitor-warning").hidden = mode === "demo" || available;
    $("sleep-monitor-warning").textContent = message;
  }
  function updateSleepPolicy() {
    $("sleep-policy-status").textContent = $("settings-form").elements.pause_on_sleep.checked ? t("已开启") : t("已关闭");
    $("sleep-policy-hint").textContent = $("settings-form").elements.pause_on_sleep.checked
      ? t("开启后，系统睡眠期间不计入自动工时。")
      : t("关闭后，若睡眠前最近一次确认 VPN 已连接，会在唤醒后估算并补入睡眠工时；这不能确认睡眠期间 VPN 一直连接。");
  }
  function addSalaryPeriod(entry, focus) {
    const row = element("div", "salary-history-row");
    const dateLabel = element("label", "", t("生效日期"));
    const date = element("input");
    date.type = "date"; date.className = "salary-effective-date";
    date.required = true; date.min = "0001-01-01"; date.max = "9999-12-31";
    date.value = entry && entry.effective_from || "";
    dateLabel.append(date);
    const amountLabel = element("label", "", t("生效后的年薪"));
    const amount = element("input");
    amount.type = "number"; amount.className = "salary-period-amount";
    amount.required = true; amount.min = "0.01"; amount.max = "10000000000"; amount.step = "0.01";
    amount.placeholder = t("输入固定年薪");
    amount.value = entry && entry.annual_salary !== undefined ? entry.annual_salary : "";
    amountLabel.append(amount);
    const remove = element("button", "secondary-button salary-remove", t("移除"));
    remove.type = "button"; remove.setAttribute("aria-label", t("移除此条薪资变更"));
    remove.addEventListener("click", function () {
      const next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      $("salary-history-empty").hidden = $("salary-history").children.length > 0;
      (next ? next.querySelector("input") : $("add-salary-period")).focus();
    });
    row.append(dateLabel, amountLabel, remove);
    $("salary-history").append(row);
    $("salary-history-empty").hidden = true;
    if (focus) date.focus();
  }
  function salaryHistoryFromForm() {
    const seen = new Set();
    return Array.from($("salary-history").children).map(function (row) {
      const effective = row.querySelector(".salary-effective-date").value;
      const amount = row.querySelector(".salary-period-amount").value.trim();
      const parsed = new Date(effective + "T00:00:00Z");
      if (!/^\d{4}-\d{2}-\d{2}$/.test(effective) || effective < "0001-01-01" || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== effective) {
        throw new Error(t("请为每条薪资变更填写有效的生效日期。"));
      }
      if (seen.has(effective)) throw new Error(t("同一天只能设置一条薪资，请合并重复的生效日期。"));
      seen.add(effective);
      if (!amount || !Number.isFinite(Number(amount)) || Number(amount) <= 0 || Number(amount) > 10000000000) {
        throw new Error(t("每条薪资变更的年薪应为大于零且不超过 100 亿的数字。"));
      }
      return { effective_from: effective, annual_salary: Number(amount) };
    }).sort(function (a, b) { return a.effective_from.localeCompare(b.effective_from); });
  }
  const settingsStatus = element("p", "field-hint");
  settingsStatus.setAttribute("role", "status"); settingsStatus.hidden = true;
  $("form-error").before(settingsStatus);
  function openSettings() {
    if (authBlocked) { showAuthError(); return; }
    if (mode === "demo") { toast(t("请切换到本机记录后修改设置。")); return; }
    if (!data || data.mode !== mode) { toast(t("本机数据尚未加载，请稍后重试。")); return; }
    updateBrowserAuthStatus();
    const form = $("settings-form"); const settings = data.settings;
    ["annual_salary", "currency", "timezone", "provider", "service_id", "status_script_path", "night_pause_start", "night_pause_end"].forEach(function (key) {
      form.elements[key].value = settings[key] === null || settings[key] === undefined ? "" : settings[key];
    });
    form.elements.theoretical_daily_hours.value = settings.theoretical_daily_hours === null || settings.theoretical_daily_hours === undefined ? 8 : settings.theoretical_daily_hours;
    $("salary-history").replaceChildren();
    $("salary-history-empty").hidden = false;
    (settings.salary_history || []).forEach(function (entry) { addSalaryPeriod(entry, false); });
    updatePrivacyControls();
    form.elements.tracking_enabled.checked = Boolean(settings.tracking_enabled);
    form.elements.pause_on_sleep.checked = settings.pause_on_sleep !== false;
    form.elements.night_pause_enabled.checked = settings.night_pause_enabled === true;
    form.elements.screen_alert_enabled.checked = settings.screen_alert_enabled !== false;
    form.elements.screen_alert_hours.value = settings.screen_alert_hours === null || settings.screen_alert_hours === undefined ? 4 : settings.screen_alert_hours;
    const screenMonitor = data.screen_monitor || {};
    $("screen-monitor-status").textContent = t(screenMonitor.message || (screenMonitor.available ? "屏幕状态检测已就绪。" : "屏幕状态暂不可用，无法可靠提醒熄屏时段。"));
    updateSleepPolicy();
    renderPowerStatus();
    form.querySelectorAll('input[name="workday"]').forEach(function (el) { el.checked = (settings.workdays || []).includes(Number(el.value)); });
    $("form-error").hidden = true;
    settingsStatus.hidden = true;
    vpnDetectionStatus = "idle";
    vpnVerification = data.vpn_verification || { service_id: "", verified: false, verified_states: [] };
    $("detected-vpn-field").hidden = true;
    $("vpn-detection-message").textContent = t("仅在你点击检测后，读取本机已配置的系统 VPN 名称与服务编号。");
    ++cliCheckSequence;
    ++vpnDetectionSequence;
    $("check-script-status").disabled = false;
    $("detect-vpn").disabled = false;
    $("script-status-message").textContent = t("尚未检查。这里仅检查 VPN 连接状态，不检查内网是否可达，也不会连接或断开 VPN。");
    $("script-status-message").classList.remove("verified");
    updateProviderField();
    settingsBaseline = captureSettingsDraft(form, $("salary-history"));
    $("settings-dialog").showModal();
    refreshAutostart();
  }
  function renderAutostart(status) {
    const control = $("autostart-enabled");
    control.checked = status.enabled === true;
    control.disabled = !status.supported || status.enabled === null || mode === "demo" || authBlocked;
    $("autostart-label").textContent = !status.supported ? t("不可用") : status.enabled === null ? t("状态未知") : status.enabled ? t("已开启") : t("已关闭");
    $("autostart-status").textContent = t(status.message || (status.enabled ? "登录后会自动启动后台服务。" : "登录后不会自动启动后台服务。"));
  }
  async function refreshAutostart() {
    const sequence = ++autostartSequence;
    const control = $("autostart-enabled");
    control.disabled = true;
    if (mode === "demo") {
      control.checked = false;
      $("autostart-label").textContent = t("演示模式不可用");
      $("autostart-status").textContent = t("切换到本机记录后可设置登录启动。");
      return;
    }
    $("autostart-label").textContent = t("读取中");
    $("autostart-status").textContent = t("正在读取启动状态…");
    try {
      const response = await fetch("/api/autostart", { cache: "no-store", credentials: "same-origin", headers: authHeaders() });
      if (response.status === 401 || response.status === 403) { showAuthError(); throw new Error(t("本机入口已失效，请重新打开。")); }
      if (!response.ok) throw new Error(t("无法读取登录启动状态，请稍后重试。"));
      const status = await response.json();
      if (sequence === autostartSequence) renderAutostart(status);
    } catch (error) {
      if (sequence !== autostartSequence) return;
      $("autostart-label").textContent = t("状态未知");
      $("autostart-status").textContent = t(error.message) || t("无法读取登录启动状态。");
    }
  }
  $("autostart-enabled").addEventListener("change", async function () {
    const control = this, before = !control.checked, desired = control.checked;
    const sequence = ++autostartSequence;
    control.disabled = true;
    $("autostart-status").textContent = t("正在更新登录启动设置…");
    try {
      const status = await post("/api/autostart", { enabled: desired });
      if (sequence !== autostartSequence) return;
      renderAutostart(status);
    } catch (error) {
      if (sequence !== autostartSequence) return;
      control.checked = before;
      $("autostart-label").textContent = t("状态未知");
      $("autostart-status").textContent = (t(error.message) || t("更新失败。")) + t(" 请重新打开设置确认当前状态。");
      control.disabled = true;
    }
  });
  function verificationMatches() {
    return vpnVerification.service_id === $("settings-form").elements.service_id.value.trim() && vpnVerification.verified === true;
  }
  function updateVerification(message) {
    const form = $("settings-form");
    const serviceId = form.elements.service_id.value.trim();
    const isVerifiedSystem = form.elements.provider.value === "verified_system";
    const matching = vpnVerification.service_id === serviceId;
    const states = matching && Array.isArray(vpnVerification.verified_states) ? vpnVerification.verified_states : [];
    const verified = verificationMatches();
    $("verified-system-verification").hidden = !isVerifiedSystem;
    $("verify-disconnected").disabled = verificationBusy || !serviceId || authBlocked;
    $("verify-connected").disabled = verificationBusy || !serviceId || authBlocked;
    $("verify-disconnected").textContent = (states.includes("disconnected") ? "✓ " : "") + t("VPN 已断开，核对状态");
    $("verify-connected").textContent = (states.includes("connected") ? "✓ " : "") + t("VPN 已连接，核对状态");
    $("verification-progress").classList.toggle("verified", verified);
    $("verification-progress").textContent = message || (verified ? t("连接与断开两种状态均已核对，可以启用计时。") : (states.length ? t("已核对 ") + (states.includes("connected") ? t("连接") : t("断开")) + t(" 状态；还需核对另一种状态。") : t("尚未核对。完成连接与断开两种状态的核对后，才能启用计时。")));
    form.elements.tracking_enabled.disabled = isVerifiedSystem && !verified;
    if (isVerifiedSystem && !verified) form.elements.tracking_enabled.checked = false;
  }
  function updateProviderField() {
    const provider = $("settings-form").elements.provider.value;
    $("provider-migration-warning").hidden = supportedSettingsProvider(provider);
    $("service-id-field").hidden = provider !== "system" && provider !== "verified_system";
    $("script-status-field").hidden = provider !== "script";
    updateVerification();
  }
  async function post(path, body) {
    if (authBlocked) { showAuthError(); throw new Error(t("请重新通过本机入口打开仪表盘。")); }
    const csrf = await currentCsrf();
    let response;
    try { response = await fetch(path, { method: "POST", credentials: "same-origin", headers: authHeaders({ "Content-Type": "application/json", "X-CSRF-Token": csrf }), body: JSON.stringify(body) }); }
    catch (_) { throw new Error(t("连接中断，操作结果未确认。请检查结果后再试。")); }
    if (response.status === 401 || response.status === 403) { throw new Error(t("连接状态已变化，操作未确认。请检查结果后再试。")); }
    let result;
    try { result = await response.json(); } catch (_) { throw new Error(t("本机服务返回了无法识别的结果。")); }
    if (!response.ok) throw new Error(t(result.error) || t("保存失败，请重试。"));
    return result;
  }
  $("settings-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    if (settingsSaving || mode === "demo") return;
    const form = event.currentTarget;
    const selectedDays = Array.from(form.querySelectorAll('input[name="workday"]:checked')).map(function (input) { return Number(input.value); });
    const salary = form.elements.annual_salary.value.trim();
    const settings = { timezone: form.elements.timezone.value.trim(), workdays: selectedDays, provider: form.elements.provider.value, service_id: form.elements.service_id.value.trim(), tracking_enabled: form.elements.tracking_enabled.checked, pause_on_sleep: form.elements.pause_on_sleep.checked, night_pause_enabled: form.elements.night_pause_enabled.checked, screen_alert_enabled: form.elements.screen_alert_enabled.checked };
    settings.status_script_path = form.elements.status_script_path.value.trim();
    if (settings.provider === "script") settings.service_id = "";
    const showError = function (message) { $("form-error").textContent = message; $("form-error").hidden = false; };
    if (!supportedSettingsProvider(settings.provider)) { showError(t("无法识别当前状态来源。请先完成旧配置迁移，或选择并确认新的状态来源。")); return; }
    if (verificationBusy) { showError(t("请等待当前 VPN 状态核对完成，再保存设置。")); return; }
    if (!hideNumbers()) {
      settings.annual_salary = salary ? Number(salary) : null;
      settings.currency = form.elements.currency.value;
      try { settings.salary_history = salaryHistoryFromForm(); }
      catch (error) { showError(t(error.message)); return; }
    }
    if (!hideTime()) {
      settings.theoretical_daily_hours = Number(form.elements.theoretical_daily_hours.value);
      settings.night_pause_start = form.elements.night_pause_start.value;
      settings.night_pause_end = form.elements.night_pause_end.value;
      settings.screen_alert_hours = Number(form.elements.screen_alert_hours.value);
    }
    if (!selectedDays.length) { showError(t("请至少选择一个理论工作日。")); return; }
    if (!hideTime() && (!Number.isFinite(settings.theoretical_daily_hours) || settings.theoretical_daily_hours <= 0 || settings.theoretical_daily_hours > 24)) { showError(t("理论每日工时需大于 0 且不超过 24 小时。")); return; }
    if (!hideTime() && (!Number.isFinite(settings.screen_alert_hours) || settings.screen_alert_hours < 1 || settings.screen_alert_hours > 24)) { showError(t("熄屏提醒阈值需要在 1–24 小时之间。")); return; }
    if (settings.tracking_enabled && settings.provider === "disabled") { showError(t("启用计时前，请先选择公司 VPN 的连接状态来源。")); return; }
    if (settings.tracking_enabled && settings.provider === "script" && !settings.status_script_path.startsWith("/")) { showError(t("启用脚本计时前，请填写脚本的绝对路径。")); return; }
    if ((settings.provider === "system" || settings.provider === "verified_system") && !settings.service_id) { showError(t("请先选择或填写已确认的系统 VPN 服务 UUID。")); return; }
    if (settings.tracking_enabled && (settings.provider === "system" || settings.provider === "verified_system") && (vpnDetectionStatus === "empty" || vpnDetectionStatus === "failed")) { showError(t("尚未检测到可用的系统 VPN，无法开始此来源的计时。请确认客户端或选择其他来源。")); return; }
    if (settings.tracking_enabled && settings.provider === "verified_system" && !verificationMatches()) { showError(t("请先完成 VPN 已连接、已断开两种状态的核对，才能启用计时。")); return; }
    const submitted = captureSettingsDraft(form, $("salary-history"));
    const numbersWereHidden = hideNumbers(), timeWereHidden = hideTime();
    settingsSaving = true;
    $("save-settings").disabled = true; $("form-error").hidden = true; settingsStatus.hidden = true;
    try {
      await post("/api/settings", settings);
      settingsBaseline = savedSettingsBaseline(settingsBaseline || submitted, submitted, numbersWereHidden, timeWereHidden);
      if (settingsDirty()) {
        settingsStatus.textContent = t("已保存本次设置；仍有未保存的修改。");
        settingsStatus.hidden = false;
      } else {
        settingsBaseline = null;
        $("settings-dialog").close();
        toast(t("本机设置已保存"));
      }
      await load();
    }
    catch (error) { showError(t(error.message) || t("保存失败")); }
    finally { settingsSaving = false; $("save-settings").disabled = false; }
  });
  $("open-settings").addEventListener("click", openSettings);
  $("extend-browser-auth").addEventListener("click", async function () {
    if (authBlocked || mode === "demo") return;
    const token = browserToken();
    if (!token) { updateBrowserAuthStatus(); return; }
    const button = this;
    button.disabled = true;
    $("browser-auth-status").textContent = t("正在延长当前浏览器授权…");
    try {
      const csrf = await currentCsrf();
      let response;
      try {
        response = await fetch("/api/browser-auth/extend", { method: "POST", credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "X-Session-Token": sessionToken, "X-Browser-Token": token }, body: "{}" });
      } catch (_) { throw new Error(t("连接中断，延长结果未确认。请重新打开设置检查，或稍后再试。")); }
      if (response.status === 401 || response.status === 403) throw new Error(t("当前浏览器授权可能已过期或服务刚刚重启，请通过本机启动入口重新打开或稍后再试。"));
      let result;
      try { result = await response.json(); } catch (_) { throw new Error(t("无法读取延长结果，请稍后检查授权状态。")); }
      if (!response.ok) throw new Error(t(result.error) || t("无法延长授权，请稍后再试。"));
      if (!Number.isFinite(result.expires_at) || result.expires_at * 1000 <= Date.now()) throw new Error(t("延长结果无效，请重新打开本机入口。"));
      const current = JSON.parse(localStorage.getItem(browserAuthKey) || "null");
      if (!current || current.token !== token) throw new Error(t("授权已更新，但当前浏览器状态发生变化；请重新打开本机入口。"));
      localStorage.setItem(browserAuthKey, JSON.stringify({ token: token, expires_at: result.expires_at }));
      updateBrowserAuthStatus();
      toast(t("当前浏览器授权已延长"));
    } catch (error) {
      $("browser-auth-status").textContent = t(error.message) || t("无法延长授权，请稍后再试。");
    } finally { button.disabled = !browserToken() || authBlocked || mode === "demo"; }
  });
  $("revoke-browser-auth").addEventListener("click", async function () {
    if (authBlocked || mode === "demo") return;
    if (settingsSaving || verificationBusy) return;
    if (!window.confirm(t("撤销后，所有浏览器都需要重新通过本机入口授权；后台计时不会停止。") + (settingsDirty() ? t("当前未保存的设置也会丢失。") : "") + t("确认撤销？"))) return;
    const button = $("revoke-browser-auth");
    button.disabled = true;
    try {
      await post("/api/browser-auth/revoke-all", {});
      try { localStorage.removeItem(browserAuthKey); sessionStorage.removeItem("hourly-access"); } catch (_) { /* Server-side revocation remains authoritative. */ }
      sessionToken = "";
      browserPairAttempted = true;
      settingsBaseline = null;
      $("settings-dialog").close();
      showAuthError();
      $("error-banner").textContent = t("已撤销所有浏览器授权。请通过本机启动入口重新打开。");
    } catch (error) {
      $("browser-auth-status").textContent = t(error.message) || t("无法撤销，请稍后重试。");
    } finally { button.disabled = false; }
  });
  $("add-salary-period").addEventListener("click", function () { addSalaryPeriod(null, true); });
  function settingsDirty() {
    return settingsBaseline !== null && JSON.stringify(captureSettingsDraft($("settings-form"), $("salary-history"))) !== JSON.stringify(settingsBaseline);
  }
  function closeSettings() {
    if (settingsSaving || verificationBusy) {
      $("form-error").textContent = t("操作正在进行，请稍候再关闭设置。");
      $("form-error").hidden = false;
      return;
    }
    if (settingsDirty() && !window.confirm(t("设置中有未保存的修改，放弃这些修改并关闭？"))) return;
    settingsBaseline = null;
    ++vpnDetectionSequence;
    ++cliCheckSequence;
    $("settings-dialog").close();
  }
  $("close-settings").addEventListener("click", closeSettings);
  $("cancel-settings").addEventListener("click", closeSettings);
  $("settings-dialog").addEventListener("cancel", function (event) { event.preventDefault(); closeSettings(); });
  window.addEventListener("beforeunload", function (event) {
    if ($("settings-dialog").open && (settingsSaving || settingsDirty())) { event.preventDefault(); event.returnValue = ""; }
  });
  $("settings-form").elements.provider.addEventListener("change", updateProviderField);
  $("settings-form").elements.pause_on_sleep.addEventListener("change", updateSleepPolicy);
  $("settings-form").elements.service_id.addEventListener("input", function () { updateVerification(); });
  $("check-script-status").addEventListener("click", async function () {
    if (authBlocked) { showAuthError(); return; }
    const sequence = ++cliCheckSequence;
    const status = $("script-status-message");
    $("check-script-status").disabled = true;
    status.classList.remove("verified");
    status.textContent = t("正在读取已保存的本机脚本状态…");
    try {
      const response = await fetch("/api/script-status", { cache: "no-store", credentials: "same-origin", headers: authHeaders() });
      if (response.status === 401 || response.status === 403) { showAuthError(); throw new Error(t("本机入口已失效，请重新打开。")); }
      const result = await response.json();
      if (!response.ok) throw new Error(t(result.error) || t("暂时无法读取脚本状态。"));
      if (sequence !== cliCheckSequence) return;
      status.textContent = t("检查结果：") + (typeof result.message === "string" ? t(result.message) : t("暂时无法确认连接状态。")) + t(" 这里只检查 VPN 连接状态。");
      status.classList.toggle("verified", result.state === "connected");
    } catch (error) {
      if (sequence === cliCheckSequence) status.textContent = t(error.message) || t("读取失败，连接状态暂不可确认。");
    } finally {
      if (sequence === cliCheckSequence) $("check-script-status").disabled = false;
    }
  });
  $("detect-vpn").addEventListener("click", async function () {
    if (authBlocked) { showAuthError(); return; }
    const sequence = ++vpnDetectionSequence;
    $("detect-vpn").disabled = true;
    $("vpn-detection-message").textContent = t("正在读取本机系统 VPN 配置…");
    $("detected-vpn-field").hidden = true;
    try {
      const response = await fetch("/api/vpn-services", { cache: "no-store", credentials: "same-origin", headers: authHeaders() });
      if (sequence !== vpnDetectionSequence) return;
      if (response.status === 401 || response.status === 403) { showAuthError(); throw new Error(t("本机入口已失效，请重新打开。")); }
      const result = await response.json();
      if (sequence !== vpnDetectionSequence) return;
      if (!response.ok) throw new Error(t(result.error) || t("无法读取本机 VPN 配置。"));
      const services = Array.isArray(result.services) ? result.services : [];
      const select = $("detected-vpn");
      select.replaceChildren();
      const placeholder = element("option", "", t("请选择已确认的公司 VPN"));
      placeholder.value = ""; select.append(placeholder);
      services.forEach(function (service) {
        const option = element("option", "", service.name || service.id);
        option.value = service.id; select.append(option);
      });
      if (!services.length) {
        vpnDetectionStatus = "empty";
        vpnVerification = { service_id: "", verified: false, verified_states: [] };
        updateVerification();
        $("vpn-detection-message").textContent = t("未检测到可用的系统 VPN。当前客户端可能不支持此路径，无法据此开始计时；请确认客户端类型或选择其他来源。");
      } else {
        vpnDetectionStatus = "loaded";
        $("detected-vpn-field").hidden = false;
        $("vpn-detection-message").textContent = t("检测到 ") + services.length + t(" 个配置。选择公司 VPN 后，服务编号会自动填入。");
      }
    } catch (error) {
      if (sequence !== vpnDetectionSequence) return;
      vpnDetectionStatus = "failed";
      $("vpn-detection-message").textContent = t(error.message) || t("检测失败，暂时无法开始此来源的计时。");
    } finally { if (sequence === vpnDetectionSequence) $("detect-vpn").disabled = false; }
  });
  $("detected-vpn").addEventListener("change", function () {
    if (this.value) $("settings-form").elements.service_id.value = this.value;
    updateVerification();
  });
  async function verifyVpn(expectedState) {
    const serviceId = $("settings-form").elements.service_id.value.trim();
    if (!serviceId || authBlocked || verificationBusy || settingsSaving) return;
    verificationBusy = true;
    ++loadSequence;
    $("save-settings").disabled = true;
    updateVerification(t("正在核对 VPN 的") + (expectedState === "connected" ? t("连接") : t("断开")) + t("状态…"));
    try {
      const result = await post("/api/verify-vpn", { service_id: serviceId, expected_state: expectedState });
      const verification = { service_id: serviceId, verified: result.verified === true, verified_states: Array.isArray(result.verified_states) ? result.verified_states : [] };
      if (data && data.settings.service_id === serviceId) {
        data.vpn_verification = verification;
        if (data.settings.provider === "verified_system" && !verification.verified) data.settings.tracking_enabled = false;
      }
      if ($("settings-form").elements.service_id.value.trim() === serviceId) {
        vpnVerification = verification;
        updateVerification(t(result.message));
      }
      await load();
    } catch (error) {
      const verification = { service_id: serviceId, verified: false, verified_states: [] };
      if (data && data.settings.service_id === serviceId) data.vpn_verification = verification;
      if ($("settings-form").elements.service_id.value.trim() === serviceId) {
        vpnVerification = verification;
        updateVerification(t(error.message) || t("核对失败，请确认 VPN 当前状态和所选服务。"));
      }
    } finally {
      verificationBusy = false;
      $("save-settings").disabled = false;
      $("verify-disconnected").disabled = !$("settings-form").elements.service_id.value.trim() || authBlocked;
      $("verify-connected").disabled = !$("settings-form").elements.service_id.value.trim() || authBlocked;
    }
  }
  $("verify-disconnected").addEventListener("click", function () { verifyVpn("disconnected"); });
  $("verify-connected").addEventListener("click", function () { verifyVpn("connected"); });
  $("locate-latest-record").addEventListener("click", locateLatestRecord);
  document.querySelectorAll("[data-trend-scale]").forEach(function (button) {
    button.addEventListener("click", function () {
      trendScaleMode = button.dataset.trendScale;
      document.querySelectorAll("[data-trend-scale]").forEach(function (item) {
        const active = item.dataset.trendScale === trendScaleMode;
        item.classList.toggle("active", active); item.setAttribute("aria-pressed", String(active));
      });
      if (data) drawDailyTrend();
    });
  });
  document.querySelectorAll("[data-heatmap-view]").forEach(function (button) {
    button.addEventListener("click", function () {
      heatmapView = button.dataset.heatmapView;
      document.querySelectorAll("[data-heatmap-view]").forEach(function (item) {
        const active = item.dataset.heatmapView === heatmapView;
        item.classList.toggle("active", active); item.setAttribute("aria-pressed", String(active));
      });
      if (data) renderHeatmap(heatmapDays());
    });
  });
  $("trend-date").addEventListener("input", function () { selectTrendDate(Number(this.value)); });
  $("daily-trend").addEventListener("pointermove", selectTrendPointer);
  $("daily-trend").addEventListener("pointerdown", selectTrendPointer);
  if (window.ResizeObserver) new ResizeObserver(function () { if (data) drawDailyTrend(); }).observe($("trend-chart"));
  else window.addEventListener("resize", function () { if (data) drawDailyTrend(); });
  if (window.ResizeObserver) new ResizeObserver(updateHeatmapOverflow).observe($("heatmap-scroll"));
  else window.addEventListener("resize", updateHeatmapOverflow);
  $("sync-now").addEventListener("click", async function () {
    $("sync-now").disabled = true;
    try { await post("/api/sync", {}); toast(t("记录已同步到本机仪表盘")); await load(); }
    catch (error) { toast(t(error.message) || t("同步失败")); }
    finally { $("sync-now").disabled = mode === "demo"; }
  });
  $("manual-pause").addEventListener("click", async function () {
    if (mode === "demo" || authBlocked || manualPauseBusy || manualPauseStateUnknown || dashboardUnavailable || !data || data.mode !== mode || (!data.settings.tracking_enabled && !(data.collector && data.collector.manual_paused))) return;
    const paused = !(data.collector && data.collector.manual_paused);
    manualPauseBusy = true;
    updateControls();
    try {
      const result = await post("/api/manual-pause", { paused: paused });
      if (data.collector && typeof result.paused === "boolean") {
        data.collector.manual_paused = result.paused;
        renderCollector();
      }
      await load();
      toast(paused ? t("自动计时已暂停") : t("已恢复检测，仍按 VPN 状态和暂停规则计时"));
    } catch (error) {
      manualPauseStateUnknown = true;
      updateControls();
      const synchronized = await load();
      toast(synchronized ? t("已重新读取计时状态，请确认后重试") : t("连接中断，计时状态未知；恢复连接后请确认"));
    }
    finally { manualPauseBusy = false; updateControls(); }
  });
  async function exportData(format) {
    if (authBlocked || mode === "demo") return;
    const button = $("export-" + format); button.disabled = true;
    try {
      const response = await fetch("/api/export?format=" + format, { credentials: "same-origin", cache: "no-store", headers: authHeaders() });
      if (response.status === 401 || response.status === 403) { showAuthError(); throw new Error(t("本机入口已失效，请重新打开。")); }
      if (!response.ok) {
        let result; try { result = await response.json(); } catch (_) { result = {}; }
        throw new Error(t(result.error) || t("导出失败，请稍后重试。"));
      }
      const blob = await response.blob(), url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = "work-time-" + new Date().toISOString().slice(0, 10) + "." + format;
      document.body.append(link); link.click(); link.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      toast(t("导出已开始"));
    } catch (error) { toast(t(error.message) || t("导出失败")); }
    finally { button.disabled = mode === "demo" || authBlocked; }
  }
  $("export-json").addEventListener("click", function () { exportData("json"); });
  $("export-csv").addEventListener("click", function () { exportData("csv"); });
  $("export-sqlite").addEventListener("click", function () {
    if (authBlocked || mode === "demo") return;
    const button = $("export-sqlite"); button.disabled = true;
    try {
      // The authenticated dashboard response established the same-origin
      // session cookie. Click synchronously to retain the browser's user
      // gesture while streaming the attachment without buffering it in JS.
      const link = document.createElement("a"); link.href = "/api/export?format=sqlite"; link.target = "_blank"; link.rel = "noopener";
      document.body.append(link); link.click(); link.remove(); toast(t("正在准备 SQLite 备份"));
    } catch (error) { toast(t(error.message) || t("导出失败")); }
    finally { button.disabled = mode === "demo" || authBlocked; }
  });
  $("restore-json").addEventListener("click", async function () {
    if (authBlocked || mode === "demo") return;
    const button = $("restore-json"), file = $("restore-file").files[0], status = $("restore-status");
    if (!file) { status.textContent = t("请先选择备份文件。"); return; }
    if (file.size > 2 * 1024 * 1024 * 1024) { status.textContent = t("SQLite 备份不能超过 2 GiB。"); return; }
    button.disabled = true;
    try {
      const header = new Uint8Array(await file.slice(0, 16).arrayBuffer());
      const isSqlite = header.length === 16 && Array.from(header).every(function (value, index) { return value === [83,81,76,105,116,101,32,102,111,114,109,97,116,32,51,0][index]; });
      let body = file, path = "/api/restore-sqlite", contentType = "application/vnd.sqlite3";
      if (!isSqlite) {
        if (file.size > 128 * 1024 * 1024 - 16) throw new Error(t("JSON 备份不能超过 128 MiB。"));
        const contents = await file.text(); let backup;
        try { backup = JSON.parse(contents); } catch (_) { throw new Error(t("无法读取备份，请选择本应用导出的 JSON 或 SQLite 文件。")); }
        if (!backup || backup.format !== "hourly-rate-backup" || backup.version !== 1) throw new Error(t("这不是支持的本应用备份。"));
        body = '{"backup":' + contents + '}'; path = "/api/restore"; contentType = "application/json";
      }
      if (!window.confirm(t("恢复将替换本机的全部工作记录和设置。系统会先保存当前数据的回滚备份，恢复后采集将暂停。确认继续？"))) return;
      status.textContent = t("正在验证和恢复，请保持页面打开…");
      const csrf = await currentCsrf();
      const response = await fetch(path, { method: "POST", credentials: "same-origin", headers: authHeaders({ "Content-Type": contentType, "X-CSRF-Token": csrf }), body: body });
      if (response.status === 401 || response.status === 403) { throw new Error(t("连接状态已变化，恢复结果未确认。请检查本机记录后再试。")); }
      let result;
      try { result = await response.json(); } catch (_) { throw new Error(t("无法读取恢复结果，请检查本机记录。")); }
      if (!response.ok) throw new Error(t(result.error) || t("恢复失败，请检查备份文件。"));
      status.textContent = t("恢复完成，采集已暂停。恢复前的备份：") + result.rollback_path;
      $("restore-file").value = "";
      await load();
      toast(t("备份已恢复，采集已暂停"));
    } catch (error) { status.textContent = t(error.message) || t("恢复失败，请稍后重试。"); }
    finally { button.disabled = mode === "demo" || authBlocked; }
  });
  function updatePrivacyControls() {
    const numbersHidden = hideNumbers(), timeHidden = hideTime();
    const toggle = $("privacy-toggle"), timeToggle = $("privacy-time-toggle");
    toggle.textContent = numbersHidden ? t("显示数字") : t("隐藏数字");
    toggle.setAttribute("aria-pressed", String(numbersHidden));
    toggle.setAttribute("aria-label", numbersHidden ? t("显示薪资与时薪数字") : t("隐藏薪资与时薪数字"));
    timeToggle.textContent = timeHidden ? t("显示时间") : t("隐藏时间");
    timeToggle.setAttribute("aria-pressed", String(timeHidden));
    timeToggle.setAttribute("aria-label", timeHidden ? t("显示工时与具体时段") : t("隐藏工时与具体时段"));
    const fields = $("salary-private-fields");
    if (numbersHidden && fields.contains(document.activeElement)) document.activeElement.blur();
    fields.querySelectorAll("input,select,button").forEach(function (field) { field.disabled = numbersHidden; });
    document.querySelectorAll(".privacy-time-field").forEach(function (group) {
      if (timeHidden && group.contains(document.activeElement)) document.activeElement.blur();
      group.querySelectorAll("input,select,button").forEach(function (field) { field.disabled = timeHidden; });
    });
    const logs = document.querySelector(".logs-link");
    if (logs && logs.getAttribute("aria-disabled") !== "true") logs.setAttribute("href", isPrivate() && !window.hourlyPrivacy.canPersist() ? "/logs.html?privacy=" + window.hourlyPrivacy.fallbackValue() : "/logs.html");
    $("trend-help").textContent = isPrivate()
      ? t("两条曲线按日期对齐。所选数值已隐藏，空白表示缺少记录；可选择日期查看记录状态。")
      : t("两条曲线按日期对齐，各自使用对应单位。空白表示缺少记录；点按图表或拖动日期滑块查看当天数据。");
  }
  $("privacy-toggle").addEventListener("click", function () { window.hourlyPrivacy.setNumbersHidden(!hideNumbers()); });
  $("privacy-time-toggle").addEventListener("click", function () { window.hourlyPrivacy.setTimeHidden(!hideTime()); });
  $("privacy-reveal-settings").addEventListener("click", function () { window.hourlyPrivacy.setNumbersHidden(false); });
  $("privacy-reveal-time-settings").addEventListener("click", function () { window.hourlyPrivacy.setTimeHidden(false); });
  window.addEventListener("hourly:privacy-change", function () {
    updatePrivacyControls();
    if (data) { updateControls(); render(); }
  });
  window.addEventListener("hourly:language-change", function () {
    // Never rebuild settings controls here: they may contain unsaved salary,
    // schedule or provider changes. Only update their labels and summaries.
    document.querySelectorAll(".salary-history-row").forEach(function (row) {
      const labels = row.querySelectorAll("label"), remove = row.querySelector(".salary-remove"), amount = row.querySelector(".salary-period-amount");
      if (labels[0] && labels[0].firstChild) labels[0].firstChild.nodeValue = t("生效日期");
      if (labels[1] && labels[1].firstChild) labels[1].firstChild.nodeValue = t("生效后的年薪");
      if (amount) amount.placeholder = t("输入固定年薪");
      if (remove) { remove.textContent = t("移除"); remove.setAttribute("aria-label", t("移除此条薪资变更")); }
    });
    screenAlertRenderKey = "";
    updatePrivacyControls(); updateBrowserAuthStatus(); updateSleepPolicy();
    if (data) { updateControls(); render(); }
    else updateTrackingControl();
    if (authBlocked) showAuthError();
  });
  updatePrivacyControls();
  document.querySelectorAll("[data-mode]").forEach(function (button) { button.addEventListener("click", function () { if (mode === button.dataset.mode) return; mode = button.dataset.mode; selectedDate = null; $("day-detail").textContent = t("选择一个日期，查看当天的工时来源、收入与实际时薪。"); load(); }); });
  document.querySelectorAll("[data-period]").forEach(function (button) { button.addEventListener("click", function () { if (period === button.dataset.period) return; period = button.dataset.period; load(); }); });
  window.addEventListener("hourly:manual-change", function () { load(); });
  load();
  setInterval(function () { if (!document.hidden && !$("settings-dialog").open && !$("manual-dialog").open) load(); }, 15000);
  document.addEventListener("visibilitychange", function () { if (!document.hidden && !$("settings-dialog").open && !$("manual-dialog").open) load(); });
})();
