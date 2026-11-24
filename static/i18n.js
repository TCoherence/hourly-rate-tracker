/* Interface language is a browser preference, independent of work settings. */
(function (root) {
  "use strict";
  // The same bootstrap can be reached through the compatibility bundle and
  // the standalone asset. Preserve preferences and avoid duplicate listeners.
  if (root.hourlyI18n) return;
  const storageKey = "hourly-rate-language";
  const english = Object.create(null);
  const valid = value => value === "system" || value === "zh" || value === "en";
  let preference = "system", language = "zh", control = null;
  let captured = false;
  const textNodes = [], attributes = [];
  try { const saved = root.localStorage.getItem(storageKey); if (valid(saved)) preference = saved; } catch (_) {}
  function systemLanguage() {
    const locale = (root.navigator && (root.navigator.language || (root.navigator.languages || [])[0])) || "en";
    return /^zh(?:-|$)/i.test(locale) ? "zh" : "en";
  }
  function format(template, values) {
    return String(template).replace(/\{([A-Za-z_][\w]*)\}/g, function (match, key) {
      return values && Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match;
    });
  }
  function t(source, values) {
    if (source === null || source === undefined) return source;
    return format(language === "en" && Object.prototype.hasOwnProperty.call(english, source) ? english[source] : source, values);
  }
  function register(entries) {
    if (!entries || typeof entries !== "object") return;
    Object.keys(entries).forEach(function (key) { if (typeof entries[key] === "string") english[key] = entries[key]; });
    if (captured) applyStatic();
  }
  function capture() {
    if (captured || !document.body) return;
    captured = true;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!node.parentElement || /^(SCRIPT|STYLE|TEXTAREA)$/.test(node.parentElement.tagName) || node.parentElement.hasAttribute("data-i18n-zh")) continue;
      const match = node.nodeValue.match(/^(\s*)([\s\S]*?)(\s*)$/);
      if (match && /[\u3400-\u9fff]/.test(match[2])) textNodes.push({ node: node, before: match[1], source: match[2], after: match[3], previous: match[2] });
    }
    document.querySelectorAll("[aria-label], [placeholder], [title]").forEach(function (el) {
      ["aria-label", "placeholder", "title"].forEach(function (attr) {
        const value = el.getAttribute(attr);
        if (value && /[\u3400-\u9fff]/.test(value)) attributes.push({ element: el, attribute: attr, source: value, previous: value });
      });
    });
  }
  function applyStatic() {
    capture();
    textNodes.forEach(function (item) {
      if (!item.node.isConnected || item.node.nodeValue !== item.before + item.previous + item.after) return;
      const next = t(item.source); item.node.nodeValue = item.before + next + item.after; item.previous = next;
    });
    attributes.forEach(function (item) {
      if (!item.element.isConnected || item.element.getAttribute(item.attribute) !== item.previous) return;
      const next = t(item.source); item.element.setAttribute(item.attribute, next); item.previous = next;
    });
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      if (el.children.length === 0) el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-zh][data-i18n-en]").forEach(function (el) {
      if (el.children.length === 0) el.textContent = el.getAttribute("data-i18n-" + language);
    });
    ["aria-label", "placeholder", "title"].forEach(function (attr) {
      document.querySelectorAll("[data-i18n-" + attr + "]").forEach(function (el) { el.setAttribute(attr, t(el.getAttribute("data-i18n-" + attr))); });
    });
    if (control) control.value = preference;
  }
  function apply(announce) {
    language = preference === "system" ? systemLanguage() : preference;
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    document.documentElement.dataset.language = language;
    const title = document.querySelector("title");
    if (title) {
      if (!title.dataset.i18nSource) title.dataset.i18nSource = title.textContent;
      title.textContent = t(title.dataset.i18nSource);
    }
    applyStatic();
    if (announce) root.dispatchEvent(new CustomEvent("hourly:language-change", { detail: { language: language, preference: preference } }));
  }
  function setPreference(value) {
    if (!valid(value)) return false;
    preference = value;
    try { root.localStorage.setItem(storageKey, value); } catch (_) {}
    apply(true); return true;
  }
  root.hourlyI18n = { t: t, register: register, language: () => language, preference: () => preference, setPreference: setPreference, apply: applyStatic };
  register({
    "公司设备是否允许运行此工具，仍需按公司的规定确认。开启后，保持本机服务运行才能持续记录。":"Check your organization's rules before running this tool on a company device. The local service must remain running to record work.",
    "实际时薪 = 已记录日期的固定日薪累计收入 ÷ 同期工作小时（VPN 与手动记录合计），不限制开始或结束时间。理论工作日以外的日期（如周末）只累计工时，不增加固定收入，因此周末加班会降低整周实际时薪。":"Effective hourly rate = fixed daily income for recorded dates ÷ work hours in the same period, including VPN and manual records, with no fixed start or end times. Non-workdays such as weekends add hours but no fixed income, lowering the weekly effective rate.",
    "尚未检查。这里只读取状态，不检查内网是否可达，也不会连接或断开 VPN。":"Not checked yet. This reads status only; it does not check internal network reachability or connect or disconnect the VPN.",
    "当前状态来源无法识别。请先完成旧配置迁移，或选择并确认新的状态来源后再保存。":"The current status source is unrecognized. Complete the old configuration migration, or select and confirm a new source before saving.",
    "手动记录会注明来源。每日总时长替代过去一天的汇总工时；补充时段与 VPN 记录合并，修正时段替代所选范围的统计。修正今天时，截止时间之后继续自动记录。原始 VPN 记录保留，撤销修正可恢复。":"Manual entries show their source. A daily total replaces that past day's total; added periods merge with VPN records, while corrections replace the selected range. For today's corrections, automatic recording continues after the cutoff. Raw VPN records are retained and can be restored by undoing the correction.",
    "按整日收入估算，今日随工时更新，缺失记录可能偏高；零工时或相关日期缺少薪资时显示「—」。薪资按生效日期计算，修改后重新计算对应时段，理论工作日设置应用于全部历史记录。第一版专注 Mac 本机记录与查看；手机导入查看留待后续，目前不提供。":"Estimates use full-day income; today's rate changes with recorded hours and missing records may make it too high. A dash is shown when work hours are zero or salary is missing. Salary changes apply from their effective dates; theoretical workday settings apply to all history. This version records and displays data locally on Mac; mobile import is not yet available.",
    "有些时段想请你确认":"Some periods need your review",
    "服务名称不能证明它属于目标 VPN。若系统检测不到服务，当前适配便无法完成；不会根据进程或网卡存在来猜测连接状态。":"A service name does not prove it is the intended VPN. If macOS cannot detect it, this adapter cannot be verified; connection state is never guessed from processes or network interfaces.",
    "正在读取上期数据…":"Loading the previous period…", "正在读取屏幕状态检测…":"Loading screen monitoring status…", "正在读取本机数据":"Loading local data", "正在读取此浏览器授权状态…":"Loading this browser's authorization status…", "正在读取睡眠识别状态…":"Loading sleep monitoring status…", "正在读取启动状态…":"Loading startup status…",
    "尚未核对。完成连接与断开两种状态的核对后，才能启用计时。":"Not verified yet. Check both connected and disconnected states before enabling tracking.", "已开启":"Enabled",
    "此开关立即生效，与下方“保存设置”分开；是否计时仍由 VPN 计时及暂停规则决定。":"This switch takes effect immediately, independently of Save settings. Tracking still follows your VPN and pause rules.",
    "此来源需要两态核对，本机脚本不需要。请选择对应的系统服务；在日常连接或断开时分别核对，确认读取的是同一个连接。按钮只检查状态，不会改变 VPN 连接。":"This source requires verification in both states; local scripts do not. Select the system service and verify it once while connected and once while disconnected. The buttons only check status and do not change the VPN connection.",
    "理论时薪 = 当前生效年薪 ÷ 本年理论工作日数 ÷ 理论每日工时。理论每日工时默认 8 小时，仅用于理论时薪。":"Theoretical hourly rate = current annual salary ÷ theoretical workdays this year ÷ theoretical daily hours. Daily hours default to eight and are used only for the theoretical rate.",
    "睡眠期间暂停计时 ·":"Pause during sleep ·",
    "这些时段在生成提醒时，屏幕长时间休眠且 VPN 自动计时。修改规则或手动修正后，当前结果可能不同，请在工作历史中核对；系统不会自动扣除工时。":"When these alerts were generated, the screen had been asleep for a long time while VPN tracking continued. Changes to rules or manual corrections may change the current result; review it in work history. No time is deducted automatically.",
    "工作占用 · 时薪仪表盘":"Time / Cost · Hourly rate dashboard",
    "工作占用首页":"Time / Cost home", "仅在此 Mac":"Only on this Mac", "仅此 Mac":"This Mac only",
    "跟随系统":"System", "浅色":"Light", "深色":"Dark", "外观主题":"Appearance", "语言":"Language", "主题":"Theme",
    "实时日志":"Live log", "工作历史":"Work history", "打开本机设置":"Open local settings", "设置":"Settings", "看见工作的真实成本":"See the real cost of work",
    "从公司 VPN 的连接状态开始，记录工作占用了多少生活。":"Start with your work VPN connection and see how much of your life work takes up.",
    "数据模式":"Data mode", "本机记录":"Local records", "演示预览":"Demo preview", "计时控制":"Tracking", "正在读取计时状态":"Loading tracking status", "暂停自动计时后，VPN 状态仍会继续检测。":"VPN status is still checked while automatic tracking is paused.", "暂停计时":"Pause tracking", "恢复计时":"Resume tracking",
    "时间范围":"Time range", "查看时间范围":"Choose a time range", "今天":"Today", "本周":"This week", "本月":"This month", "本季度":"This quarter", "本半年":"This half-year", "今年 YTD":"Year to date", "过去一年":"Past year",
    "数据隐私显示":"Privacy display", "隐藏数字":"Hide numbers", "隐藏时间":"Hide time", "隐藏薪资与时薪数字":"Hide salary and hourly rates", "隐藏工时与具体时段":"Hide work hours and time ranges",
    "时薪与工作时间":"Hourly rate and work hours", "实际时薪":"Effective hourly rate", "VPN 口径":"VPN basis", "理论时薪":"Theoretical hourly rate", "工作占用":"Work time", "所选时段收入 ÷ 总工时":"Income in selected period ÷ total work hours", "与理论时薪相比":"Compared with theoretical rate", "与上期相比":"Compared with previous period", "与上一时段对比":"Comparison with previous period", "等待记录":"Waiting for records", "/ 小时":"/ hour", "小时":"hours", "当前生效年薪 ÷ 本年理论工时":"Current annual salary ÷ this year's theoretical work hours", "已记录日期":"Days recorded", "按整日收入估算，今日随工时更新，缺失记录可能偏高。":"Estimated using a full day's income. Today's rate changes as hours are recorded; missing records may make it too high.",
    "每日工时与时薪":"Daily hours and hourly rate", "所选时段":"Selected period", "两条曲线按日期对齐，各自使用对应单位。空白表示缺少记录；点按图表或拖动日期滑块查看当天数据。":"The two lines share dates and use their own units. Gaps indicate missing records. Select the chart or date slider for daily details.", "纵轴范围":"Vertical axis", "聚焦变化":"Focus on changes", "从零开始":"Start at zero", "纵轴按记录自动调整。":"The vertical axis adjusts to your records.", "这个时段还没有可绘制的记录。":"No records to plot for this period.", "查看日期":"Select date", "当日工时":"Hours worked", "当日实际时薪":"Effective hourly rate", "正在读取每日记录…":"Loading daily records…",
    "实际时薪按当天固定日薪 ÷ 当天工时计算；有工时但不足 1 小时时按 1 小时估算，不改变记录的工时。非理论工作日不分配额外收入，有工时的单日实际时薪为 0；整周按总收入 ÷ 真实总工时计算。今日与记录不完整的日期会随补充记录变化；零工时或缺少薪资时，时薪留空。":"Daily effective rate is fixed daily income ÷ hours worked. For a day with less than one hour recorded, the estimate uses one hour without changing the recorded duration. Non-workdays add hours but no extra fixed income. Weekly rates use total income ÷ actual hours. Estimates change as records are added; rates are blank when hours are zero or salary is unavailable.",
    "工作占用热力图":"Work time heatmap", "颜色说明":"Color legend", "少":"Less", "多":"More", "未知":"Unknown", "默认显示今天前后三个月。颜色表示当天合计工时，灰色斜纹表示缺少记录，淡灰色为未来日期；描边标出今天。":"Shows three months before and after today. Colors represent daily work hours; stripes indicate missing records, pale gray indicates future days, and an outline marks today.", "热力图范围":"Heatmap range", "最近半年":"Recent six months", "全年":"Full year", "定位最近记录":"Find latest record", "↔ 左右滑动查看前后三个月":"↔ Scroll to see the surrounding months", "全年工作时间，点击日期查看详情":"Annual work hours; choose a date for details", "选择一个日期，查看当天的工时来源、收入与实际时薪。":"Select a date to see its sources, income, and effective hourly rate.", "尚未发生":"Future date",
    "最近的工作片段":"Recent work periods", "VPN / 手动记录 / 睡眠":"VPN / manual / sleep", "没有操作电脑不会自动扣除时间。按天估算的手动记录没有具体时段，不显示为工作片段。":"Inactivity is not automatically deducted. Daily-total estimates have no time ranges and are not shown here.", "记录留在本机":"Your records stay local", "尚未启用采集":"Tracking is not enabled", "同步目的地":"Sync destination", "同步频率":"Sync frequency", "每 1 分钟":"Every minute", "最近同步":"Last synced", "等待同步":"Pending", "0 条":"0", "立即同步到本机仪表盘":"Sync local dashboard now", "没有云端上传、第三方统计或外部字体。薪资与记录保存在本机。":"No cloud upload, third-party analytics, or external fonts. Salary and records stay on this Mac.",
    "导出本机数据":"Export local data", "导出 SQLite 备份":"Export SQLite backup", "导出 JSON":"Export JSON", "导出每日 CSV":"Export daily CSV", "SQLite 和 JSON 含薪资、设置及原始记录，可用于恢复；CSV 是每日统计。请妥善保存导出文件。":"SQLite and JSON contain salary, settings, and raw records and can be restored. CSV contains daily summaries. Store exports securely.", "从备份恢复":"Restore from backup", "恢复会替换本机记录，并先保存当前数据的回滚备份；恢复后需要重新启用采集。CSV 仅用于查看，不能用于恢复。":"Restoring replaces local records after creating a rollback backup. Tracking must be re-enabled afterward. CSV is for viewing only and cannot be restored.", "选择 JSON 或 SQLite 备份":"Choose a JSON or SQLite backup", "检查并恢复":"Review and restore", "查看保存位置与计算口径":"Storage and calculation details", "时间有边界，数据也有。":"Your time has boundaries. So does your data.",
    "本机设置":"Local settings", "关闭设置":"Close settings", "设置只保存在这台 Mac。演示数据不会写入真实记录。":"Settings stay on this Mac. Demo data is never written to your real records.", "时间已隐藏；其他设置仍可保存。":"Time is hidden; other settings can still be saved.", "显示时间并编辑":"Show time and edit", "收入与理论工时":"Income and theoretical work hours", "数字已隐藏；其他设置仍可保存。":"Numbers are hidden; other settings can still be saved.", "显示数字并编辑薪资":"Show numbers and edit salary", "初始年薪（此前适用）":"Initial annual salary (for earlier dates)", "可留空":"Optional", "币种":"Currency", "USD 美元":"USD · US dollar", "CNY 人民币":"CNY · Chinese yuan", "EUR 欧元":"EUR · euro", "GBP 英镑":"GBP · pound sterling", "CAD 加元":"CAD · Canadian dollar", "JPY 日元":"JPY · Japanese yen", "初始年薪用于第一条生效日期之前；未添加变更时用于所有日期。留空表示此前薪资未知。":"The initial salary applies before the first effective date, or to all dates if no changes are added. Leave blank if unknown.", "薪资变更":"Salary changes", "添加生效日期":"Add effective date", "还没有薪资变更，可在调薪或开始任职时添加。":"No salary changes yet. Add one when your pay or employment starts.", "每条年薪从所设时区的生效日期起，持续到下一条生效日期。所有时段使用同一币种，不做汇率换算；保存后会重新计算相关历史统计。":"Each salary applies from its effective date in the selected time zone until the next effective date. All periods use one currency without conversion. Saving recalculates affected history.",
    "理论每日工时（小时）":"Theoretical daily hours", "默认每天 8 小时，仅用于计算理论时薪。实际工时按记录与暂停规则计算，不受固定上下班时间限制。":"Defaults to 8 hours and is used only for the theoretical hourly rate. Actual work hours use your records and pause rules, without fixed start or end times.", "时区":"Time zone", "新安装自动识别系统时区，无法识别时使用 UTC。修改时区会重新划分历史日期。":"New installations detect the system time zone, falling back to UTC. Changing it reassigns historical dates.", "理论工作日":"Theoretical workdays", "一":"Mon", "二":"Tue", "三":"Wed", "四":"Thu", "五":"Fri", "六":"Sat", "日":"Sun", "以每年实际日历中的理论工作日分配固定日薪；未勾选的日期（如周末）只累计 VPN 工时，不增加固定收入。暂不单独扣除节假日。":"Fixed daily income is allocated across theoretical workdays in the calendar year. Unselected days, such as weekends, add hours but no fixed income. Holidays are not excluded separately yet.",
    "公司 VPN":"Work VPN", "连接状态来源":"Connection status source", "无法识别的来源":"Unrecognized source", "尚未配置":"Not configured", "本机状态脚本":"Local status script", "需两态核对的系统 VPN":"System VPN requiring two-state verification", "macOS 系统 VPN":"macOS system VPN", "需要确认客户端支持读取状态。无法确认时保留为未知，不猜测工作状态。":"The client must support reading its status. If it cannot be confirmed, the status remains unknown.", "状态脚本绝对路径":"Absolute path to status script", "例如 /Users/you/bin/work-status":"For example, /Users/you/bin/work-status", "检查已保存的脚本状态":"Check saved script status", "读取本机脚本状态":"Read local script status", "只运行你信任的脚本。脚本需输出 connected、disconnected 或 unknown；执行失败、超时或输出无效时按未知处理。路径修改后请先保存，再检查状态。":"Run only scripts you trust. The script must output connected, disconnected, or unknown. Failures, timeouts, and invalid output are treated as unknown. Save a changed path before checking status.", "系统 VPN 服务 UUID":"System VPN service UUID", "仅系统 VPN 需要，填入已确认的服务 UUID":"For system VPN only; enter the verified service UUID", "选择已检测的系统 VPN":"Select a detected system VPN", "请选择":"Select", "检测本机 VPN":"Detect local VPNs", "仅在你点击检测后，读取本机已配置的系统 VPN 名称与服务编号。":"Configured system VPN names and service IDs are read only when you click Detect.", "系统 VPN 的两态核对":"Verify both system VPN states", "VPN 已连接，核对状态":"Verify connected", "VPN 已断开，核对状态":"Verify disconnected", "启用本机 VPN 计时":"Enable local VPN tracking", "只读取连接状态；不读取屏幕、文件或消息。":"Reads connection status only, not your screen, files, or messages.", "完成本机设置后，才会读取 VPN 连接状态。":"VPN status is read after local setup is complete.",
    "睡眠期间暂停计时":"Pause tracking during sleep", "仅指整台 Mac 睡眠；熄屏、锁屏本身不会暂停。":"Only full Mac sleep counts; turning off or locking the screen alone does not pause tracking.", "开启后，系统睡眠期间不计入自动工时。":"When enabled, Mac sleep is excluded from automatically recorded hours.", "切换会重新计算已记录的睡眠时段，手动记录不受影响。唤醒后会自动恢复检测。":"Changing this recalculates recorded sleep periods without changing manual entries. Detection resumes after wake.", "夜间自动暂停计时":"Automatically pause overnight", "保留 VPN 状态检测；到结束时间后自动恢复计入工时。":"VPN checks continue and work tracking resumes at the end time.", "暂停开始":"Pause starts", "恢复计时":"Resume tracking", "按所设时区每天生效，支持跨午夜。修改后会重算历史；原始 VPN 记录保留，手动记录优先。":"Applies daily in the selected time zone and can cross midnight. Changes recalculate history; raw VPN records remain and manual entries take priority.", "熄屏过久时提醒确认":"Flag long screen-off periods", "屏幕休眠且 VPN 仍在计时达到阈值时提醒；不会自动扣除工时。":"Flag periods when the screen is asleep and VPN tracking continues past the threshold; no time is deducted automatically.", "连续熄屏提醒阈值（小时）":"Consecutive screen-off threshold (hours)", "默认 4 小时，可设置 1–24 小时。夜间暂停、手动暂停、整机睡眠或 VPN 状态未知会中断这段时间。":"Defaults to 4 hours; choose 1–24 hours. Overnight or manual pauses, Mac sleep, or an unknown VPN status interrupt the period.",
    "启动与后台运行":"Startup and background operation", "登录后自动启动":"Start at login", "登录后自动启动 ·":"Start at login ·", "读取中":"Loading", "登录此 Mac 账户后在后台启动，不会自动打开浏览器。":"Start in the background after logging into this Mac account, without opening a browser.", "浏览器授权":"Browser authorization", "本页只管理当前浏览器的授权。授权后，14 天内重启服务无需再次授权；可在到期前手动延长。":"This page manages only this browser's authorization. It remains valid across service restarts for 14 days and can be extended before expiry.", "其他浏览器需要分别通过本机启动入口打开并授权；浏览器数据清除或授权过期后，也需重新打开入口。":"Authorize each browser separately through the local launch entry. Reopen it after browser data is cleared or authorization expires.", "延长此浏览器授权":"Extend this browser's authorization", "撤销所有浏览器授权":"Revoke all browser authorizations", "取消":"Cancel", "保存设置":"Save settings",
    "关闭工作历史":"Close work history", "选择日期查看工作记录，也可以添加或修改手动记录。可以填写多个时段，或记录过去一天的总小时。":"Select a date to view records or add and edit manual entries. Enter multiple periods or a daily total for a past date.", "正在读取本机工作历史…":"Loading local work history…", "工作历史日历":"Work history calendar", "工作历史日历上个月":"Previous month", "工作历史日历下个月":"Next month", "选择日期":"Choose a date", "工时颜色与热力图一致：由少到多，斜纹表示未知":"Colors match the heatmap from less to more; stripes indicate unknown", "已有手动记录":"Has manual entry", "回到今天":"Back to today", "跳转到日期":"Go to date", "当天工作记录":"Daily work record", "未保存预览":"Unsaved preview", "当天记录分段":"Daily record segments", "正在读取当天分段…":"Loading daily segments…", "记录方式":"Entry type", "修正已记录的工作时段":"Correct recorded work periods", "补充工作时段（与自动记录合并）":"Add work periods (merged with automatic records)", "我只记得总小时（过去日期）":"I only remember total hours (past dates)", "按本机设置的时区填写。":"Enter times in the configured time zone.", "当天总时长（小时）":"Total hours for the day", "快捷填写总小时":"Quick total hours", "8 小时":"8 hours", "10 小时":"10 hours", "11 小时":"11 hours", "12 小时":"12 hours", "＋ 添加一段工作":"＋ Add a work period", "可从中点拆分后调整时间，也可合并下一段；保存后生效。24 小时制，结束选 24:00 表示当天结束；跨午夜的工作请分两天记录。":"Split a period at its midpoint and adjust it, or merge it with the next. Changes take effect after saving. Use 24-hour time; 24:00 means the end of the day. Enter overnight work on each date separately.", "沿用之前的手动记录":"Reuse previous manual entry", "手动记录预览":"Manual entry preview", "这次填写的时长":"Duration entered", "24 小时工作时段预览":"24-hour work-period preview", "仅预览，保存后生效。":"Preview only; changes take effect after saving.", "备注（可选）":"Note (optional)", "例如：根据记忆估算，或补记晚间工作":"For example: estimated from memory", "保存记录":"Save entry", "查看已有手动记录":"View manual entries", "编辑今天":"Edit today", "尚无手动记录。":"No manual entries yet."
  });
  root.addEventListener("storage", function (event) {
    if (event.key !== storageKey && event.key !== null) return;
    preference = valid(event.newValue) ? event.newValue : "system"; apply(true);
  });
  root.addEventListener("languagechange", function () { if (preference === "system") apply(true); });
  // Set the document language immediately; DOM nodes are captured after parsing.
  language = preference === "system" ? systemLanguage() : preference;
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  document.documentElement.dataset.language = language;
  document.addEventListener("DOMContentLoaded", function () {
    control = document.getElementById("language-mode");
    if (control) control.addEventListener("change", function () { setPreference(control.value); });
    apply(false);
  });
})(window);
