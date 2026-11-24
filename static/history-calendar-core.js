"use strict";

(function () {
  function loc(text) { return window.hourlyI18n ? window.hourlyI18n.t(text) : text; }
  if (window.hourlyI18n) window.hourlyI18n.register({
    "。": ".",
    " 小时": " hours",
    "具体数字已隐藏；可通过色块查看大致工作情况。": "Times are hidden; colors still show an approximate view.",
    "无法读取当月工时": "Could not load this month's hours",
    "当月工时加载失败，请重新打开工作历史。": "Could not load this month's hours. Reopen work history.",
    "，已有手动记录": ", manual record exists",
    "，无手动记录": ", no manual record",
    "，尚未发生": ", upcoming",
    "，缺少记录": ", missing data",
    "，已有记录，具体数字已隐藏": ", recorded; times hidden",
    "，总工时 ": ", total work time ",
    "尚未发生。": "Upcoming.",
    "当天没有足够的记录。": "Not enough records for this day.",
    "当天已有工作记录，具体数字已隐藏。": "Work was recorded; times are hidden. ",
    "包含手动记录。": "Includes manual records.",
    "当天总工时 ": "Total work time: ",
    "，其中 VPN 原始记录 ": ", including raw VPN time: ",
    "已使用手动总时长作为当天合计。": "The manual daily total is used. ",
    "已使用手动修正时段作为当天合计。": "Manually corrected intervals determine the daily total. ",
    "已合并手动时间段，重叠部分只计一次。": "Manual intervals are merged; overlaps count once. ",
    "下方可添加手动记录。": "You can add manual records below. ",
    " VPN 原始记录保留，可查看或恢复。": "Raw VPN records are preserved and can be viewed or restored."
});
  // One scale is used by both the dashboard and the work-history calendar.
  function level(hours) {
    if (!hours) return 0;
    if (hours < 3) return 1;
    if (hours < 6) return 2;
    if (hours < 9) return 3;
    return 4;
  }
  window.HourlyHistoryCalendar = { level: level };
  const grid = document.getElementById("manual-calendar-days");
  if (!grid) return;
  let month = "", days = null, pending = "", generation = 0;
  const details = document.createElement("p");
  details.className = "field-hint history-day-details";
  details.setAttribute("role", "status");
  document.getElementById("manual-selected-label").parentElement.after(details);
  function format(hours) {
    const value = Number(Number(hours || 0).toFixed(2));
    const en = window.hourlyI18n && window.hourlyI18n.language && window.hourlyI18n.language() === "en";
    return value + (en ? (value === 1 ? " hour" : " hours") : loc(" 小时"));
  }
  function privacyHidden() {
    if (window.hourlyPrivacy && typeof window.hourlyPrivacy.isTimeHidden === "function") return window.hourlyPrivacy.isTimeHidden();
    if (document.documentElement.dataset.privacyTime) return document.documentElement.dataset.privacyTime === "hidden";
    return document.documentElement.dataset.privacy === "hidden";
  }
  function render() {
    // Clear prior details before inspecting cached data; a request already in
    // flight must always render according to the current privacy setting.
    const hidden = privacyHidden();
    if (hidden) details.textContent = loc("具体数字已隐藏；可通过色块查看大致工作情况。");
    const buttons = grid.querySelectorAll("button[data-date]");
    if (!buttons.length) return;
    const next = buttons[0].dataset.date.slice(0, 7);
    // An earlier request can still be in flight when the user returns to a
    // previously viewed month. Invalidate it on each navigation, including
    // A → B → A, so its late result cannot replace the current month's data.
    if (month !== next) { generation++; month = next; days = null; pending = ""; }
    if (!days && pending !== month) {
      const requested = month, requestGeneration = generation; pending = requested;
      let token = "";
      try { token = sessionStorage.getItem("hourly-access") || ""; } catch (_) {}
      const headers = { "X-Session-Token": token };
      try {
        const saved = JSON.parse(localStorage.getItem("hourly-browser-auth-v1") || "null");
        if (saved && typeof saved.token === "string" && Number.isFinite(saved.expires_at) && saved.expires_at * 1000 > Date.now()) headers["X-Browser-Token"] = saved.token;
      } catch (_) {}
      fetch("/api/history-month?month=" + encodeURIComponent(requested), { credentials: "same-origin", cache: "no-store", headers: headers })
        .then(function (response) { if (!response.ok) throw new Error(loc("无法读取当月工时")); return response.json(); })
        .then(function (data) { if (month === requested && generation === requestGeneration) { days = new Map(data.days.map(function (day) { return [day.date, day]; })); render(); } })
        .catch(function () { if (month === requested && generation === requestGeneration) details.textContent = loc("当月工时加载失败，请重新打开工作历史。"); })
        .finally(function () { if (pending === requested && generation === requestGeneration) pending = ""; });
    }
    buttons.forEach(function (button) {
      const date = button.dataset.date, day = days && days.get(date);
      button.classList.remove("history-unknown", "history-future", "history-level-0", "history-level-1", "history-level-2", "history-level-3", "history-level-4");
      if (!day) return;
      const future = day.status === "future", unknown = day.status === "unknown";
      button.classList.add(future ? "history-future" : unknown ? "history-unknown" : "history-level-" + level(day.work_hours));
      let small = button.querySelector("small");
      if (!small) { small = document.createElement("small"); button.append(small); }
      small.textContent = hidden || future || unknown ? "" : Number(Number(day.work_hours).toFixed(2)) + "h";
      const manual = day.manual_kind ? loc("，已有手动记录") : loc("，无手动记录");
      button.setAttribute("aria-label", date.replaceAll("-", "/") + (future ? loc("，尚未发生") : unknown ? loc("，缺少记录") : hidden ? loc("，已有记录，具体数字已隐藏") : loc("，总工时 ") + format(day.work_hours)) + (future ? "" : manual));
      if (button.classList.contains("selected")) {
        details.textContent = future ? loc("尚未发生。") : unknown ? loc("当天没有足够的记录。") : hidden ? loc("当天已有工作记录，具体数字已隐藏。") + (day.manual_kind ? loc("包含手动记录。") : "") :
          loc("当天总工时 ") + format(day.work_hours) + loc("，其中 VPN 原始记录 ") + format(day.vpn_work_hours) + loc("。") +
          (day.manual_kind ? (day.manual_kind === "daily_total" ? loc("已使用手动总时长作为当天合计。") : day.manual_kind === "intervals_override" ? loc("已使用手动修正时段作为当天合计。") : loc("已合并手动时间段，重叠部分只计一次。")) : loc("下方可添加手动记录。")) + loc(" VPN 原始记录保留，可查看或恢复。");
      }
    });
  }
  window.addEventListener("hourly:privacy-change", render);
  window.addEventListener("hourly:language-change", render);
  window.addEventListener("hourly:manual-change", function () { generation++; days = null; pending = ""; render(); });
  new MutationObserver(render).observe(grid, { childList: true });
  document.getElementById("open-manual").addEventListener("click", function () { generation++; month = ""; days = null; pending = ""; });
})();
