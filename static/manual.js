"use strict";

(function () {
  function loc(text) {
    return typeof window !== "undefined" && window.hourlyI18n ? window.hourlyI18n.t(text) : text;
  }
  function english() { return typeof window !== "undefined" && window.hourlyI18n && window.hourlyI18n.language() === "en"; }
  function formattedHours(value) { return value + (english() ? (Number(value) === 1 ? " hour" : " hours") : " 小时"); }
  if (typeof window !== "undefined" && window.hourlyI18n) {
    window.hourlyI18n.register({
    "请选择完整的开始和结束时间。": "Choose complete start and end times.",
    "时间应使用 00:00–24:00 的 24 小时制。": "Use 24-hour time from 00:00 to 24:00.",
    "日期已变化，不能保存之前的至今时段；草稿仍在。请先记录内容再重新打开工作历史。": "The date changed. This current-day draft cannot be saved; note your changes before reopening work history.",
    "至今须晚于这一段的开始时间；请调整开始时间。": "Present must be later than the start time.",
    "至今": "Present",
    "未找到该工作时段。": "Work interval not found.",
    "未找到要调整的时间点。": "Time to adjust not found.",
    "请选择有效时间。": "Choose a valid time.",
    "现有时段有重叠或顺序不对，请先调整后再添加。": "Fix overlapping or out-of-order intervals before adding one.",
    "现有时段超出可调整范围，请先调整后再添加。": "Adjust intervals outside the editable range before adding one.",
    "没有空闲时间可添加，请先调整或拆分已有时段。": "No free time remains. Adjust or split an existing interval first.",
    "每天可以填写 1 至 12 段工作。": "Enter 1 to 12 work intervals per day.",
    "第 ": "Interval ",
    " 段的结束须晚于开始；跨午夜工作请分两天记录。": " must end after it starts; record work across midnight on separate days.",
    "每天最多填写 12 段工作。": "A day can contain at most 12 work intervals.",
    "至少需要 2 分钟的时段才能拆分。": "An interval must be at least 2 minutes long to split.",
    "请选择相邻的两个时段。": "Choose two adjacent intervals.",
    "请先检查两个时段的开始和结束时间。": "Check both intervals' start and end times.",
    "无法读取最新工作时段。": "Could not read the latest work intervals.",
    "当前草稿有重叠或顺序不对，请先调整；草稿未改变。": "Fix overlapping or out-of-order intervals first. Your draft is unchanged.",
    "修正截止时间没有向后更新。": "The correction cutoff has not advanced.",
    "最新工作时段无效，请重新打开工作历史。": "The latest intervals are invalid. Reopen work history.",
    "更新后超过 12 段，请先调整草稿再试；草稿未改变。": "Updating would exceed 12 intervals. Adjust your draft first; it is unchanged.",
    "当天记录或时区已变化，无法安全更新修正范围；草稿仍在，请记录后重新打开工作历史。": "The day's records or timezone changed, so the correction range cannot be updated safely. Note your draft and reopen work history.",
    "当前时段正在自动记录，不能扩大修正范围；草稿仍在，连接结束后可重新读取。": "Tracking is active, so the correction range cannot be extended. Your draft remains; reload after the connection ends.",
    "请选择今天或过去的日期。": "Choose today or an earlier date.",
    "备注最多 500 字。": "Notes can contain at most 500 characters.",
    "今天请填写具体工作时段；总小时用于过去的日期。": "Enter intervals for today. Daily totals are for past dates.",
    "当天总时长应在 0 到 24 小时之间。": "The daily total must be between 0 and 24 hours.",
    "请等待当天记录加载完成，取得修正截止时间。": "Wait for the day's correction cutoff to load.",
    "请选择记录方式。": "Choose a recording method.",
    "可浏览日历和色块；工时及具体时段已隐藏。显示时间后可编辑；未保存的修改会保留。": "Browse the calendar and colors while times are hidden. Show times to edit; unsaved changes are preserved.",
    "显示时间": "Show times",
    "备注已隐藏；保存时会保留备注，显示数字后可编辑。": "Notes are hidden but retained on save. Show numbers to edit.",
    "跳转到日期": "Go to date",
    " · 今天": " · Today",
    "本机授权已失效，请重新打开工作历史后再试。": "Local authorization expired. Reopen work history and try again.",
    "本机连接信息不完整，请稍后重试。": "Local connection information is incomplete. Try again.",
    "暂时无法连接本机服务。": "Cannot connect to the local service right now.",
    "连接中断，操作结果未确认。请检查工作记录后再试。": "Connection lost; the outcome is unconfirmed. Check your records before retrying.",
    "本机入口尚未授权或已失效，请通过 start-hourly-rate.command 重新打开。": "Local access is missing or expired. Reopen using start-hourly-rate.command.",
    "连接状态已变化，操作未确认。请检查工作记录后再试。": "Connection status changed; the action is unconfirmed. Check your records before retrying.",
    "无法读取本机工作记录，请稍后重试。": "Could not read local records. Try again.",
    "操作失败，请重试。": "Action failed. Try again.",
    "次日 ": "Next day ",
    "正在自动记录 · 暂不可修正": "Automatic tracking · editing unavailable",
    "此时段正在自动记录，暂时不能修正；结束后重新打开即可修改。": "This interval is being tracked automatically. Reopen it after tracking ends to edit.",
    " 段 · 正在自动记录 · 暂不可修正": " · tracking automatically; editing unavailable",
    "保护范围 ": "Protected range: ",
    " – 至今": " – Present",
    "从 ": "From ",
    " 起保留自动记录（最近确认 ": ", automatic tracking is protected (last confirmed ",
    "），此段暂时不能修正；连接结束后重新打开即可修改。起点按分钟向前取整保护。": "). Reopen after the connection ends to edit. The start is rounded down to protect the full minute.",
    "自动记录状态已变化。为保留草稿，请先记录当前修改，再重新打开工作历史；未保存的内容不会自动写入。": "Tracking status changed. Note your draft and reopen work history; unsaved changes are never written automatically.",
    "自动记录状态已变化；为保护当前时段，请重新打开工作历史再修改。": "Tracking status changed. Reopen work history to protect the current interval.",
    "当前连接仍在记录，请切回修正；若要使用补充，请先撤销当天修正。": "Tracking is active. Use correction, or undo today's correction before adding a supplement.",
    "暂时无法刷新自动记录状态；当前草稿的修正范围不会变化。": "Cannot refresh tracking status. Your draft's correction range is unchanged.",
    "查看状态变化前的草稿": "View draft before status changed",
    "这是状态变化时的快照，可选中复制；当前编辑内容仍保留在下方。": "This snapshot captures the draft when status changed. Select to copy; your current edits remain below.",
    "状态变化前的草稿快照": "Draft snapshot before status changed",
    "按总小时记录：": "Daily total: ",
    "工作时段：": "Work intervals:",
    " 段：": ": ",
    "（当时的至今）": " (present at that time)",
    "备注：": "Note: ",
    "正在读取当天分段…": "Loading day's intervals…",
    "当天记录分段": "Day's recorded intervals",
    "当天按手动总小时估算，以下采样分段不能代表该估算的具体时间。时间为 ": "This day uses a manually estimated total. The samples below do not represent its exact intervals. Timezone: ",
    "以下是实际采样与手动记录计算后的分段；未确认状态不会算作已连接。时间为 ": "Intervals below are based on samples and manual records; unconfirmed status is not treated as connected. Timezone: ",
    "已连接": "Connected",
    "已断开": "Disconnected",
    "未知": "Unknown",
    "手动": "Manual",
    "手动修正": "Manual correction",
    "手动暂停": "Manual pause",
    "夜间暂停": "Night pause",
    "睡眠估算": "Sleep estimate",
    "睡眠暂停": "Sleep pause",
    "睡眠未知": "Sleep unknown",
    "没有可展示的具体时段；按总小时估算的记录不会虚构分段。": "No intervals to display. Daily total estimates do not invent specific intervals.",
    "已计入": "Counted",
    "未计入": "Not counted",
    "记录": "Record",
    "已保存的截止后手动工作：": "Saved manual work after cutoff: ",
    "。这些时段会保留；如需修改，可撤销当天修正，或在次日编辑完整记录。": ". These intervals are preserved. To change them, undo today's correction or edit the complete record tomorrow.",
    "查看原始 VPN 状态": "View raw VPN status",
    "撤销当天修正": "Undo today's correction",
    "撤销当天修正并恢复修正前的记录？原始 VPN 采样不受影响。": "Undo today's correction and restore the previous record? Raw VPN samples remain intact.",
    "已撤销当天修正": "Today's correction was undone",
    "用当天已计时段作为修正起点": "Use recorded intervals as a starting point",
    "已将当天已计时段填入编辑器。": "The day's recorded intervals have been loaded into the editor. ",
    "可将当天已计时段填入编辑器。": "You can load the day's recorded intervals into the editor. ",
    "自动采样精确到秒，填入时按分钟取整；请核对并调整后保存。": "Samples are precise to the second and rounded to minutes here. Review before saving. ",
    "修正截至 ": "Correction cutoff: ",
    "，其后继续自动记录；重新打开可刷新截止时间。": ". Automatic tracking continues afterwards; reopen to refresh the cutoff. ",
    "保存后仅修正时段计工时，其余时间（包括未知时间）均不计入。": "After saving, only corrected intervals count; other time, including unknown time, does not. ",
    "原始 VPN 记录保留，可撤销恢复。": "Raw VPN records are preserved; corrections can be undone.",
    "今天的修正截至 ": "Today's correction cutoff: ",
    "无法读取当天分段：": "Could not load day's intervals: ",
    "确认手动工作时间": "Confirm manual work time",
    "修正范围截至 ": "Correction cutoff: ",
    " 将作为你手动填写的工作时间计入。原始记录、未填写的未知时间和之后的自动记录会保留。": " will be counted as manually entered work. Raw records, unspecified unknown time, and later automatic records are preserved.",
    "继续编辑": "Continue editing",
    "确认保存": "Confirm save",
    "这一天有尚未保存的修改。放弃这些修改并继续？": "This day has unsaved changes. Discard them and continue?",
    "更新可修正范围": "Refresh correction range",
    "保留草稿，检查最新记录并在确认后更新截止时间": "Keep the draft, check recent records and update the cutoff after confirmation",
    "工作时段编辑方式": "Work interval editor",
    "滑动时间轴": "Timeline",
    "精确选择时间": "Choose exact times",
    "撤销上一步": "Undo last change",
    "撤销本次编辑中的上一个时段操作": "Undo the last interval change in this draft",
    "请重启本机服务后使用撤销": "Restart the local service to use undo",
    "自动记录或修正范围已变化，无法安全撤销；当前草稿和撤销记录仍在。": "Tracking or the correction range changed. Undo is unsafe; your draft and undo history are preserved.",
    "该步骤与正在自动记录的时段重叠，暂时不能撤销；当前草稿仍在。": "That step overlaps an active tracking interval and cannot be undone yet. Your draft is preserved.",
    "已撤销上一步，修改尚未保存。": "Last change undone; your draft is not saved.",
    "至今 · 之后无新增手动工作，自动计时仍按当前状态运行": "Present · No new manual work after the last interval; automatic tracking follows its current status",
    "自动记录状态已变化。草稿中这一段的原结束时间为 ": "Tracking status changed. This interval's original draft end was ",
    "；请先记下草稿再重新打开工作历史。": ". Note your draft before reopening work history.",
    "手动预览随时间更新；保存时截止当下，之后由自动计时决定。": "This manual preview advances with time. Saving ends it now; automatic tracking determines what follows.",
    "拖动开始时间；结束时间为至今。": "Drag the start; the end is present.",
    "拖动两端或用方向键按分钟调整，点击轨道可定位。": "Drag either end or use arrow keys for one-minute adjustments. Click the track to position.",
    "时段有重叠、顺序不对或超出可调整范围，请调整或移除后再保存。": "Intervals overlap, are out of order, or exceed the editable range. Adjust or remove them before saving.",
    "可调整范围 ": "Editable range: ",
    "；不会越过相邻时段。": "; adjacent intervals cannot be crossed.",
    "每天最多 12 段": "Maximum 12 intervals per day",
    "至少 2 分钟才能拆分": "At least 2 minutes needed to split",
    "先从中点拆分，之后可调整时间": "Split at the midpoint, then adjust",
    "保存修改": "Save changes",
    "保存手动记录": "Save manual record",
    "日期已变化，原来的今日修正范围不能再保存。草稿仍在，请先记录内容再重新打开工作历史。": "The date changed and today's old correction range can no longer be saved. Note your draft and reopen work history.",
    "按 ": "Using ",
    "本机时区": "local timezone",
    " 计算。": ". ",
    "已加载当天记录，可直接修改。": "The day's record is loaded and ready to edit. ",
    "加载中": "Loading",
    "，其后继续自动记录。": "; automatic tracking continues afterwards. ",
    "修正后仅所填时段计工时，其余时间（包括未知时间）不计入。": "After correction only entered intervals count, including no unknown time. ",
    "原始 VPN 记录保留。": "Raw VPN records are preserved. ",
    "今天只记录已经经过的部分。": "Today only elapsed time is recorded.",
    "沿用 ": "Use ",
    " 的手动记录": " ",
    "还没有可沿用的更早手动记录": "No earlier manual record to reuse",
    " 段": " ",
    "拆分": "Split",
    "拆分第 ": "Split interval ",
    " 段工作": " ",
    "与下一段合并": "Merge with next",
    "将第 ": "Merge interval ",
    " 段与下一段合并": " with next",
    "合并后两段之间的 ": "Merging will count the ",
    " 分钟也会计入工时，本次填写的总工时将增加 ": " minutes between intervals, increasing the entered total by ",
    " 分钟。确定合并吗？": " minutes. Merge?",
    "移除": "Remove",
    "移除第 ": "Remove interval ",
    "开始": "Start",
    "结束": "End",
    "小时": " hour",
    "分钟": " minute",
    "开始时间": "start time",
    "结束时间": "end time",
    "拖动两端或用方向键按分钟调整。": "Drag either end or use arrow keys to adjust by a minute.",
    " 年 ": " / ",
    " 月": " ",
    " 今天": " Today",
    "，已有手动记录，具体数字已隐藏": ", manual record exists; numbers hidden",
    "，已有补录 ": ", manually recorded ",
    " 小时": " hours",
    "，尚未发生": ", upcoming",
    "，未补录": ", no manual record",
    "有未保存修改": "Unsaved changes",
    "已加载手动记录": "Manual record loaded",
    "未保存预览": "Unsaved preview",
    "24 小时预览：": "24-hour preview: ",
    "时段有重叠或顺序不对，请调整或移除后再保存；原草稿不会自动改变。": "Intervals overlap or are out of order. Adjust or remove them before saving; the original draft will not change automatically.",
    "按整天总量估算，不虚构具体时段。保存后替代当天合计工时。": "Estimated from the daily total; no specific intervals are invented. Saving replaces the daily total.",
    "所填末段超出截止的部分将另作手动工作，保存时请确认。": "The part of the final interval past the cutoff will be recorded as manual work; confirm on save. ",
    "截止后继续自动记录。": "Automatic tracking continues after the cutoff. ",
    "保存后以这些时段作为当天工时。": "These intervals become the day's work time on save. ",
    "原始 VPN 记录保留，可撤销修正。仅预览，保存后生效。": "Raw VPN records are preserved and the correction can be undone. Preview only until saved.",
    "保存后与 VPN 工时去重。": "On save, overlapping VPN time is counted only once. ",
    "今天只累计已过去的部分。": "Only elapsed time counts today. ",
    "仅预览，保存后生效。": "Preview only until saved.",
    "上方预览不含已保存的受保护时段；这些时段会继续保留。": "The preview excludes protected saved intervals; they will remain preserved.",
    "请补全有效的工作时段": "Enter valid work intervals",
    "，但当天分段刷新失败；请重新打开工作历史查看。": ", but refreshing the day's intervals failed. Reopen work history to view them.",
    "，但无法刷新记录；请关闭并重新打开工作历史。": ", but records could not be refreshed. Close and reopen work history.",
    "查看已有手动记录（": "View manual records (",
    " 天）": " days)",
    "手动估算 · ": "Manual estimate · ",
    "整日修正 · ": "Daily correction · ",
    "补充时段 · ": "Supplemental intervals · ",
    "编辑": "Edit",
    "编辑 ": "Edit manual record for ",
    "撤销": "Undo",
    "撤销 ": "Undo ",
    " 的修正并恢复修正前的记录？原始 VPN 采样不受影响。": "'s correction and restore its previous record? Raw VPN samples remain intact.",
    " 的手动记录？这一天会恢复使用原始 VPN 记录。": "'s manual record? The day will use raw VPN records again.",
    "已撤销手动记录": "Manual record undone",
    "本机工作记录信息不完整，请重新打开页面。": "Local work record information is incomplete. Reopen the page.",
    "日期或草稿已变化，未更新修正范围；请检查后重试。": "The date or draft changed. The range was not updated; check it and retry.",
    "自动记录状态已变化；草稿仍在，请先记下修改并重新打开工作历史。": "Tracking status changed. Note your preserved draft and reopen work history.",
    "至今包含正在自动记录的时段，请等待记录结束后再修正；草稿仍在。": "Present includes active tracking. Wait for it to end before correcting; your draft remains.",
    "最新同步尚未覆盖至今，请稍候同步后重试；草稿仍在。": "The latest sync does not reach the present. Sync and retry; your draft remains.",
    "将修正截止从 ": "Update the correction cutoff from ",
    " 更新到 ": " to ",
    "会保留当前草稿，并加入新增范围内已记录的工作时段（比当前填写合计增加 ": "The draft will be preserved and recorded work in the added range included (increasing the current total by ",
    " 分钟）。": " minutes). ",
    "新增范围内未列出的时间，包括未知时间，将不计入工时。秒级采样按分钟取整，极短片段可能无法表示，请核对。": "Time not listed in the added range, including unknown time, will not count. Seconds are rounded to minutes; very short intervals may not be represented. Review carefully. ",
    "原始采样保留，修正可以撤销。更新后不会自动保存，截止之后的自动记录仍保留。": "Raw samples remain and corrections can be undone. Updating does not save automatically; later automatic records remain.",
    "修正范围已更新至 ": "Correction range updated to ",
    "。上方分段仍为上次加载的快照；保存后会刷新。原始 VPN 记录保留，可撤销修正。": ". The intervals above are from the previous snapshot; they refresh after saving. Raw VPN records remain and corrections can be undone.",
    "修正范围已更新，请核对后保存。": "Correction range updated. Review before saving. ",
    "有时段晚于新截止 ": "Some intervals end after the new cutoff ",
    "，请调整后再保存。": ". Adjust before saving.",
    "无法更新修正范围；草稿仍在。": "Could not update the correction range. Your draft is preserved.",
    "工作记录尚未加载，请关闭后重试。": "Work records are not loaded. Close and try again.",
    "日期已变化，不能保存之前的今日修正；草稿仍在，请先记录内容再重新打开工作历史。": "The date changed; today's old correction cannot be saved. Note your draft and reopen work history.",
    "工作时段不能重叠，且须按时间先后排列；请先调整或移除冲突时段。草稿仍在。": "Work intervals must be ordered and cannot overlap. Adjust or remove conflicts; your draft remains.",
    "本机服务需要重启后才能保存本次修改；草稿仍在，请先记下修改。": "Restart the local service to save this change. Note your preserved draft first.",
    "该时段可能与自动记录重叠，请先核对；草稿仍在。": "This interval may overlap automatic tracking. Review it; your draft remains.",
    "本机服务需要重启后才能保存至今；草稿仍在，请先记下修改。": "Restart the local service to save to present. Note your preserved draft first.",
    "状态或草稿已变化，请核对后重试；草稿仍在。": "Status or the draft changed. Review and retry; your draft remains.",
    "今天修正的时段不能晚于截止时间 ": "Today's correction cannot extend past the cutoff ",
    "（未知）": "(unknown)",
    "；之后的时段继续自动记录。": "; automatic tracking continues afterwards.",
    "已保存修改": "Changes saved",
    "参考 ": "Based on ",
    "。": ".",
    "、": ", ",
    "？\n\n": "?\n\n",
    "当天只有总时长估算，不能推测具体时段。": "Only an estimated daily total is available; specific intervals cannot be inferred.",
    "当天发生时区偏移变化，无法安全地自动转换成分钟时段。": "The UTC offset changed on this day, so intervals cannot be converted safely.",
    "当天发生时区偏移变化，无法安全地自动转换成分钟时段。今天请使用补充时段。": "The UTC offset changed today, so intervals cannot be converted safely. Use supplemental intervals instead.",
    "当天超过 12 个时段，无法自动填入，请手动选择需要保留的时段。": "This day has more than 12 intervals; choose which to retain manually.",
    "当前连接包含先前修正，为保留已有调整，请在连接结束后重新打开工作历史再修改。": "This active connection includes an earlier correction. Reopen work history after it ends to preserve your changes.",
    "自动记录状态已变化，请重新检查工作历史；草稿仍在": "Tracking status changed. Review work history; your draft is preserved.",
    "当前连接仍在记录，请先撤销当天修正，再使用补充": "Tracking is active. Undo today's correction before adding supplemental time.",
    "当前连接仍在记录，不能修正进行中的时段；请重新打开工作历史": "Tracking is active; the current interval cannot be corrected. Reopen work history.",
    "当前连接包含先前修正，请等待连接结束后再修改": "This connection includes a previous correction. Wait until it ends to edit.",
    "当天记录已发生变化，请重新读取后再修正": "The day's record changed. Reload it before correcting.",
    "至今记录状态无效": "The present interval status is invalid.",
    "至今记录状态与当前修正不符": "The present interval status does not match this correction.",
    "至今只能用于今天的修正": "Present is available only when correcting today.",
    "至今时间无效，请刷新当前记录后重试": "The present time is invalid. Reload the current record and try again.",
    "至今必须是最后一段且晚于修正截止时间": "Present must be the final interval and later than the correction cutoff.",
    "今天的修正时段不能超过加载时的截止时间": "Today's correction cannot extend beyond the loaded cutoff.",
    "今天发生时区偏移变化，无法安全修正，请改用补充时段": "The UTC offset changes today, so correction is unavailable. Use supplemental intervals instead.",
    "请重新读取今天的记录，取得有效的修正截止时间": "Reload today's record to get a valid correction cutoff.",
    "请重新读取今天的记录，取得修正版本": "Reload today's record to get the current correction version.",
    "保留的手动时段超过 12 段，请先整理后再保存": "More than 12 manual intervals would be retained. Organize them before saving."
});
  }
  function validDate(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "") || value.slice(0, 4) === "0000") return false;
    const date = new Date(value + "T12:00:00Z");
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
  }
  function monthDays(month) {
    if (!validDate(month + "-01")) return [];
    const first = new Date(month + "-01T12:00:00Z"), end = new Date(first);
    const offset = (first.getUTCDay() + 6) % 7;
    end.setUTCMonth(end.getUTCMonth() + 1, 0);
    return Array.from({ length: 42 }, function (_, index) {
      const day = index - offset + 1;
      return day > 0 && day <= end.getUTCDate() ? month + "-" + String(day).padStart(2, "0") : null;
    });
  }
  function minute(value, allowEnd) {
    if (allowEnd && value === "24:00") return 1440;
    if (!/^\d{2}:\d{2}$/.test(value || "")) throw new Error(loc("请选择完整的开始和结束时间。"));
    const parts = value.split(":").map(Number);
    if (parts[0] > 23 || parts[1] > 59) throw new Error(loc("时间应使用 00:00–24:00 的 24 小时制。"));
    return parts[0] * 60 + parts[1];
  }
  function clock(value) { return String(Math.floor(value / 60)).padStart(2, "0") + ":" + String(value % 60).padStart(2, "0"); }
  // "Present" is an editing mode, not an instruction to extend tracking or
  // change the server's protected correction cutoff.
  function currentTimeChoice(date, today, zone, index, count, hidden, now) {
    if (hidden || date !== today || index !== count - 1 || count < 1 || !zone) return null;
    try {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23"
      }).formatToParts(new Date(now === undefined ? Date.now() : now));
      const value = Object.fromEntries(parts.map(function (part) { return [part.type, part.value]; }));
      if (value.year + "-" + value.month + "-" + value.day !== date) return null;
      const result = value.hour + ":" + value.minute;
      minute(result, false);
      return result;
    } catch (_) { return null; }
  }
  function defaultPresentIndex(date, today, zone, count, active, unavailable, now) {
    if (active || count < 1) return -1;
    return currentTimeChoice(date, today, zone, count - 1, count, false, now) === null ? -1 : count - 1;
  }
  function resolvePresentTime(date, today, zone, index, count, hidden, start, now) {
    const value = currentTimeChoice(date, today, zone, index, count, hidden, now);
    if (!value) throw new Error(loc("日期已变化，不能保存之前的至今时段；草稿仍在。请先记录内容再重新打开工作历史。"));
    if (minute(value, false) <= minute(start, false)) throw new Error(loc("至今须晚于这一段的开始时间；请调整开始时间。"));
    return value;
  }
  // Ignore the moving end when deciding whether the user changed the draft.
  // Merely watching time pass must not mark a record as edited or save it.
  function draftFingerprint(value, present) {
    const copy = Object.assign({}, value);
    if (present && Array.isArray(value.intervals) && value.intervals.length) {
      copy.intervals = value.intervals.map(function (span, index) {
        return index === value.intervals.length - 1 ? Object.assign({}, span, {end: "至今"}) : Object.assign({}, span);
      });
    }
    return JSON.stringify(copy);
  }
  function adjustBoundary(start, end, side, value) {
    if (side === "start") {
      end = Math.max(1, end);
      start = Math.min(Math.max(0, value), end - 1);
    } else {
      start = Math.min(1439, start);
      end = Math.max(Math.min(1440, value), start + 1);
    }
    return [start, end];
  }
  // The two handles share one window so their physical position and the
  // printed axis always use the same scale. Invalid older drafts are left
  // untouched and retain a full-day repair window.
  function intervalWindow(values, index, limit) {
    if (!Array.isArray(values) || !values[index]) throw new Error(loc("未找到该工作时段。"));
    const ceiling = Number.isInteger(limit) ? Math.max(1, Math.min(1440, limit)) : 1440;
    const start = minute(values[index].start, false), end = minute(values[index].end, true);
    const lower = index ? minute(values[index - 1].end, true) : 0;
    const upper = index + 1 < values.length ? Math.min(ceiling, minute(values[index + 1].start, false)) : ceiling;
    if (lower > start || end > upper || end <= start || lower >= upper) return { min: 0, max: 1440, conflict: true };
    return { min: lower, max: upper, conflict: false };
  }
  function adjustIntervalBoundary(values, index, side, value, limit) {
    const window = intervalWindow(values, index, limit);
    const start = minute(values[index].start, false), end = minute(values[index].end, true);
    if (side !== "start" && side !== "end") throw new Error(loc("未找到要调整的时间点。"));
    if (!Number.isFinite(value)) throw new Error(loc("请选择有效时间。"));
    if (window.conflict) return adjustBoundary(start, end, side, value);
    return side === "start" ? [Math.max(window.min, Math.min(Math.round(value), end - 1)), end] :
      [start, Math.min(window.max, Math.max(Math.round(value), start + 1))];
  }
  function intervalsInOrder(values, allowEmpty) {
    if (!Array.isArray(values) || (!allowEmpty && !values.length) || values.length > 12) return false;
    try {
      let previousEnd = 0;
      for (const value of values) {
        const start = minute(value.start, false), end = minute(value.end, true);
        if (start < previousEnd || end <= start) return false;
        previousEnd = end;
      }
      return true;
    } catch (_) { return false; }
  }
  function insertionForGap(values, limit) {
    if (!intervalsInOrder(values, true)) throw new Error(loc("现有时段有重叠或顺序不对，请先调整后再添加。"));
    const ceiling = Number.isInteger(limit) ? Math.max(0, Math.min(1440, limit)) : 1440;
    const gaps = []; let cursor = 0;
    for (let i = 0; i < values.length; i++) {
      const start = minute(values[i].start, false), end = minute(values[i].end, true);
      if (start > ceiling || end > ceiling) throw new Error(loc("现有时段超出可调整范围，请先调整后再添加。"));
      if (start > cursor) gaps.push({ start: cursor, end: start, index: i });
      cursor = end;
    }
    if (cursor < ceiling) gaps.push({ start: cursor, end: ceiling, index: values.length });
    const gap = gaps[gaps.length - 1];
    if (!gap) throw new Error(loc("没有空闲时间可添加，请先调整或拆分已有时段。"));
    let start = gap.index === values.length ? gap.start : Math.max(gap.start, gap.end - 60);
    if (!values.length && gap.start <= 540 && gap.end > 540) start = 540;
    return { index: gap.index, interval: { start: clock(start), end: clock(Math.min(gap.end, start + 60)) } };
  }
  function normalizeIntervals(values, allowEmpty) {
    if (!Array.isArray(values) || (!allowEmpty && values.length < 1) || values.length > 12) throw new Error(loc("每天可以填写 1 至 12 段工作。"));
    const ranges = values.map(function (value, index) {
      const start = minute(value.start, false), end = minute(value.end, true);
      if (end <= start) throw new Error(loc("第 ") + (index + 1) + loc(" 段的结束须晚于开始；跨午夜工作请分两天记录。"));
      return [start, end];
    }).sort(function (a, b) { return a[0] - b[0]; });
    const merged = [];
    ranges.forEach(function (range) {
      const previous = merged[merged.length - 1];
      if (previous && range[0] < previous[1]) previous[1] = Math.max(previous[1], range[1]);
      else merged.push(range.slice());
    });
    return { intervals: merged.map(function (range) { return { start: clock(range[0]), end: clock(range[1]) }; }),
      minutes: merged.reduce(function (sum, range) { return sum + range[1] - range[0]; }, 0), ranges: merged };
  }
  function hasOverlappingIntervals(values) {
    const normalized = normalizeIntervals(values, true);
    const rawMinutes = values.reduce(function (total, span) {
      return total + minute(span.end, true) - minute(span.start, false);
    }, 0);
    return rawMinutes > normalized.minutes;
  }
  function splitInterval(values, index) {
    if (!Array.isArray(values) || values.length >= 12 || !values[index]) throw new Error(loc("每天最多填写 12 段工作。"));
    const span = values[index], start = minute(span.start, false), end = minute(span.end, true);
    if (end - start < 2) throw new Error(loc("至少需要 2 分钟的时段才能拆分。"));
    const midpoint = clock(start + Math.floor((end - start) / 2));
    const result = values.slice();
    result.splice(index, 1, { start: span.start, end: midpoint }, { start: midpoint, end: span.end });
    return result;
  }
  function mergeIntervals(values, index) {
    if (!Array.isArray(values) || !values[index] || !values[index + 1]) throw new Error(loc("请选择相邻的两个时段。"));
    const first = values[index], second = values[index + 1];
    const a = [minute(first.start, false), minute(first.end, true)], b = [minute(second.start, false), minute(second.end, true)];
    if (a[1] <= a[0] || b[1] <= b[0]) throw new Error(loc("请先检查两个时段的开始和结束时间。"));
    const gap = Math.max(0, Math.max(a[0], b[0]) - Math.min(a[1], b[1]));
    const result = values.slice();
    result.splice(index, 2, { start: clock(Math.min(a[0], b[0])), end: clock(Math.max(a[1], b[1])) });
    const added = normalizeIntervals(result).minutes - normalizeIntervals(values).minutes;
    return { intervals: result, gap: gap, added: added };
  }
  // Keep the user's draft and include only newly observed work in the newly
  // extended correction window. Adjacent ranges retain deliberate split points.
  function rebaseIntervals(values, observed, oldTime, newTime) {
    if (!Array.isArray(values) || !Array.isArray(observed)) throw new Error(loc("无法读取最新工作时段。"));
    if (!intervalsInOrder(values, true)) throw new Error(loc("当前草稿有重叠或顺序不对，请先调整；草稿未改变。"));
    const low = minute(oldTime, false), high = minute(newTime, false);
    if (high <= low) throw new Error(loc("修正截止时间没有向后更新。"));
    const original = normalizeIntervals(values, true);
    const extra = observed.map(function (span) {
      const start = minute(span.start, false), end = minute(span.end, true);
      if (end <= start) throw new Error(loc("最新工作时段无效，请重新打开工作历史。"));
      return [Math.max(start, low), Math.min(end, high)];
    }).filter(function (span) { return span[1] > span[0]; });
    const combined = original.ranges.concat(extra).sort(function (a, b) { return a[0] - b[0]; });
    const merged = [];
    combined.forEach(function (span) {
      const previous = merged[merged.length - 1];
      if (previous && span[0] < previous[1]) previous[1] = Math.max(previous[1], span[1]);
      else merged.push(span.slice());
    });
    const splits = original.ranges.slice(1).filter(function (span, index) {
      return original.ranges[index][1] === span[0];
    }).map(function (span) { return span[0]; });
    const rebased = merged.flatMap(function (span) {
      const inner = splits.filter(function (cut) { return span[0] < cut && cut < span[1]; });
      const points = [span[0]].concat(inner, [span[1]]);
      return points.slice(1).map(function (end, index) { return [points[index], end]; });
    });
    if (rebased.length > 12) throw new Error(loc("更新后超过 12 段，请先调整草稿再试；草稿未改变。"));
    return { intervals: rebased.map(function (span) { return { start: clock(span[0]), end: clock(span[1]) }; }),
      added: rebased.reduce(function (total, span) { return total + span[1] - span[0]; }, 0) - original.minutes };
  }
  function validateRefreshSnapshot(original, latest, date, zone) {
    if (!original || !latest || latest.date !== date || latest.timezone !== zone ||
        typeof original.edit_revision !== "string" || !/^[a-f0-9]{64}$/.test(original.edit_revision) ||
        latest.edit_revision !== original.edit_revision || !Number.isInteger(original.edit_cutoff) ||
        !Number.isInteger(latest.edit_cutoff) || latest.edit_cutoff < original.edit_cutoff ||
        latest.today_override_available !== true || !Array.isArray(latest.editable_intervals)) {
      throw new Error(loc("当天记录或时区已变化，无法安全更新修正范围；草稿仍在，请记录后重新打开工作历史。"));
    }
    const active = latest.active_tracking;
    if (active) {
      const locked = Date.parse(active.locked_from) / 1000;
      if (active.save_blocked || !Number.isFinite(locked) || latest.edit_cutoff > locked) {
        throw new Error(loc("当前时段正在自动记录，不能扩大修正范围；草稿仍在，连接结束后可重新读取。"));
      }
    }
    return active || null;
  }
  function buildEntry(draft, today, editCutoff, editRevision) {
    if (!validDate(draft.date) || draft.date > today) throw new Error(loc("请选择今天或过去的日期。"));
    const entry = { date: draft.date, kind: draft.kind, note: (draft.note || "").trim() };
    if (entry.note.length > 500) throw new Error(loc("备注最多 500 字。"));
    if (entry.kind === "daily_total") {
      if (entry.date >= today) throw new Error(loc("今天请填写具体工作时段；总小时用于过去的日期。"));
      if (String(draft.hours).trim() === "" || !Number.isFinite(Number(draft.hours)) || Number(draft.hours) < 0 || Number(draft.hours) > 24) throw new Error(loc("当天总时长应在 0 到 24 小时之间。"));
      entry.hours = Number(draft.hours);
    } else if (entry.kind === "intervals" || entry.kind === "intervals_override") {
      if (entry.kind === "intervals_override" && entry.date === today) {
        if (!Number.isFinite(editCutoff) || typeof editRevision !== "string" || !/^[a-f0-9]{64}$/.test(editRevision)) throw new Error(loc("请等待当天记录加载完成，取得修正截止时间。"));
        entry.edit_cutoff = editCutoff;
        entry.edit_revision = editRevision;
      }
      entry.intervals = normalizeIntervals(draft.intervals, entry.kind === "intervals_override" && entry.date === today).intervals;
    }
    else throw new Error(loc("请选择记录方式。"));
    return entry;
  }
  function initialEditorKind(entry, date, today) {
    if (entry && entry.kind === "daily_total") return "daily_total";
    return "intervals_override";
  }
  function shouldPrefillIntervals(entry, date, today) {
    return date <= today && (!entry || entry.kind === "intervals" || entry.kind === "intervals_override" && (date === today || Number.isFinite(entry.edit_cutoff)));
  }
  // Exercise the same pure date/time rules with Node, without a DOM dependency.
  if (typeof module === "object" && module.exports) {
    module.exports = { validDate: validDate, monthDays: monthDays, normalizeIntervals: normalizeIntervals, hasOverlappingIntervals: hasOverlappingIntervals, buildEntry: buildEntry, adjustBoundary: adjustBoundary, intervalWindow: intervalWindow, adjustIntervalBoundary: adjustIntervalBoundary, intervalsInOrder: intervalsInOrder, insertionForGap: insertionForGap, initialEditorKind: initialEditorKind, shouldPrefillIntervals: shouldPrefillIntervals, splitInterval: splitInterval, mergeIntervals: mergeIntervals, currentTimeChoice: currentTimeChoice, defaultPresentIndex: defaultPresentIndex, resolvePresentTime: resolvePresentTime, draftFingerprint: draftFingerprint, rebaseIntervals: rebaseIntervals, validateRefreshSnapshot: validateRefreshSnapshot };
    return;
  }

  const $ = function (id) { return document.getElementById(id); };
  const form = $("manual-form"), dialog = $("manual-dialog");
  let entries = [], today = "", timezone = "", csrfToken = "", selectedDate = "", calendarMonth = "";
  let busy = false, baseline = "", rebasePending = false, presentRow = null, presentTrackingConflict = false, presentClosed = false;
  let conflictSnapshot = null;
  let dayRequest = 0, dayData = null, dayLoading = false, dayWasPrefilled = false;
  let activeTracking = null, trackingRefreshPending = false, trackingStatusUnavailable = false;
  let intervalEditor = "timeline";
  // An older running service may not yet expose the new undo script. Keep
  // the editor usable until it can be restarted, without fabricating undo.
  const undoAvailable = Boolean(window.hourlyDraftUndo && window.hourlyDraftUndo.createDraftUndo);
  const undo = undoAvailable ? window.hourlyDraftUndo.createDraftUndo() : {
    record: function () {}, endGroup: function () {}, peek: function () { return null; },
    discard: function () {}, reset: function () {}
  };
  let dragSequence = 0, dragGroup = null;
  let privacyBrowseDate = "", lastPrivacyHidden = false;
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  const saveStatus = element("p", "field-hint");
  saveStatus.setAttribute("role", "status"); saveStatus.hidden = true;
  $("manual-error").before(saveStatus);
  function statusMessage(text) { saveStatus.textContent = text; saveStatus.hidden = !text; }
  const privacyNotice = element("div", "manual-privacy-notice");
  privacyNotice.append(element("p", "", loc("可浏览日历和色块；工时及具体时段已隐藏。显示时间后可编辑；未保存的修改会保留。")));
  const privacyReveal = element("button", "secondary-button", loc("显示时间"));
  privacyReveal.type = "button";
  privacyReveal.addEventListener("click", function () {
    if (window.hourlyPrivacy && typeof window.hourlyPrivacy.setTimeHidden === "function") window.hourlyPrivacy.setTimeHidden(false);
  });
  privacyNotice.append(privacyReveal);
  privacyNotice.hidden = true;
  form.querySelector(".dialog-heading").after(privacyNotice);
  const noteField = form.elements.note.closest("label");
  noteField.classList.add("manual-note-field");
  const noteNotice = element("p", "field-hint manual-note-privacy-notice", loc("备注已隐藏；保存时会保留备注，显示数字后可编辑。"));
  noteField.before(noteNotice);
  const privateDateJump = element("label", "manual-date-jump manual-privacy-date-jump", loc("跳转到日期"));
  const privateDateInput = element("input");
  privateDateInput.type = "date";
  privateDateJump.append(privateDateInput);
  form.querySelector(".manual-date-jump").after(privateDateJump);
  privateDateInput.addEventListener("change", function () {
    const value = privateDateInput.value;
    privateDateInput.value = privacyBrowseDate || selectedDate;
    if (validDate(value) && value <= today && value !== (privacyBrowseDate || selectedDate)) loadDate(value);
  });
  function privacyHidden() {
    if (window.hourlyPrivacy && typeof window.hourlyPrivacy.isTimeHidden === "function") return window.hourlyPrivacy.isTimeHidden();
    if (document.documentElement.dataset.privacyTime) return document.documentElement.dataset.privacyTime === "hidden";
    if (document.documentElement.dataset.privacy === "hidden") return true;
    try { return localStorage.getItem("hourly-privacy-hidden") === "1"; } catch (_) { return false; }
  }
  function numbersHidden() {
    if (window.hourlyPrivacy && typeof window.hourlyPrivacy.isNumbersHidden === "function") return window.hourlyPrivacy.isNumbersHidden();
    if (document.documentElement.dataset.privacyNumbers) return document.documentElement.dataset.privacyNumbers === "hidden";
    return document.documentElement.dataset.privacy === "hidden";
  }
  function applyManualPrivacy() {
    const hidden = privacyHidden();
    privacyNotice.hidden = !hidden;
    noteNotice.hidden = !numbersHidden();
    if (hidden && !lastPrivacyHidden) privacyBrowseDate = selectedDate;
    if (!hidden && lastPrivacyHidden && dialog.open && selectedDate) {
      const target = privacyBrowseDate;
      if (target && target !== selectedDate && !dirty() && !busy) {
        lastPrivacyHidden = false;
        privacyBrowseDate = "";
        loadDate(target, true);
        return;
      }
      // Never overwrite an unsaved draft simply because another day was browsed.
      calendarMonth = selectedDate.slice(0, 7);
      form.elements.date.value = selectedDate;
      $("manual-selected-label").textContent = selectedDate.replaceAll("-", "/") + (selectedDate === today ? loc(" · 今天") : "");
      privacyBrowseDate = "";
    }
    lastPrivacyHidden = hidden;
    if (calendarMonth) renderCalendar();
    if (dialog.open) updateFields();
  }
  window.addEventListener("hourly:privacy-change", applyManualPrivacy);
  window.addEventListener("storage", function (event) { if (event.key === "hourly-privacy-v2" || event.key === "hourly-privacy-hidden" || event.key === null) applyManualPrivacy(); });
  form.addEventListener("submit", function (event) { if (privacyHidden()) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);
  applyManualPrivacy();
  function token() { try { return sessionStorage.getItem("hourly-access") || ""; } catch (_) { return ""; } }
  function authHeaders() {
    const headers = { "X-Session-Token": token() };
    try {
      const saved = JSON.parse(localStorage.getItem("hourly-browser-auth-v1") || "null");
      if (saved && typeof saved.token === "string" && Number.isFinite(saved.expires_at) && saved.expires_at * 1000 > Date.now()) headers["X-Browser-Token"] = saved.token;
    } catch (_) { /* Existing browser session remains usable. */ }
    return headers;
  }
  async function request(path, body) {
    const options = { credentials: "same-origin", cache: "no-store", headers: authHeaders() };
    if (body !== undefined) {
      const session = await fetch("/api/session", { credentials: "same-origin", cache: "no-store", headers: authHeaders() });
      if (!session.ok) throw new Error(loc("本机授权已失效，请重新打开工作历史后再试。"));
      const sessionData = await session.json();
      if (typeof sessionData.csrf_token !== "string" || !sessionData.csrf_token) throw new Error(loc("本机连接信息不完整，请稍后重试。"));
      csrfToken = sessionData.csrf_token;
      options.method = "POST"; options.headers["Content-Type"] = "application/json";
      options.headers["X-CSRF-Token"] = csrfToken; options.body = JSON.stringify(body);
    }
    let response;
    try { response = await fetch(path, options); }
    catch (_) { throw new Error(body === undefined ? loc("暂时无法连接本机服务。") : loc("连接中断，操作结果未确认。请检查工作记录后再试。")); }
    if (response.status === 401 || response.status === 403) throw new Error(body === undefined ? loc("本机入口尚未授权或已失效，请通过 start-hourly-rate.command 重新打开。") : loc("连接状态已变化，操作未确认。请检查工作记录后再试。"));
    let result;
    try { result = await response.json(); } catch (_) { throw new Error(loc("无法读取本机工作记录，请稍后重试。")); }
    if (!response.ok) throw new Error(result.error || loc("操作失败，请重试。"));
    return result;
  }
  function segmentTime(value, date) {
    if (typeof value !== "string") return "—";
    return (value.slice(0, 10) !== date ? loc("次日 ") : "") + value.slice(11, 19);
  }
  function cutoffTime(value) {
    if (!Number.isFinite(value)) return "";
    try {
      return new Intl.DateTimeFormat("zh-CN", { timeZone: timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(value * 1000));
    } catch (_) { return ""; }
  }
  function trackingTime(value, seconds) {
    if (typeof value !== "string") return "";
    const parsed = new Date(value);
    if (!Number.isFinite(parsed.getTime())) return "";
    try {
      return new Intl.DateTimeFormat("zh-CN", { timeZone: timezone, hour: "2-digit", minute: "2-digit", ...(seconds ? { second: "2-digit" } : {}), hourCycle: "h23" }).format(parsed);
    } catch (_) { return ""; }
  }
  function trackingSaveBlocked() {
    if (!currentTimeChoice(selectedDate, today, timezone, 0, 1, false)) return false;
    if (presentTrackingConflict) return true;
    if ((dayData && dayData.active_tracking && dayData.active_tracking.save_blocked) || (activeTracking && activeTracking.save_blocked)) return true;
    const lockedFrom = activeTracking && Date.parse(activeTracking.locked_from) / 1000;
    return Number.isFinite(lockedFrom) && dayData && Number.isFinite(dayData.edit_cutoff) && lockedFrom < dayData.edit_cutoff;
  }
  function renderActiveTracking() {
    const box = $("manual-active-tracking");
    const live = !trackingStatusUnavailable && currentTimeChoice(selectedDate, today, timezone, 0, 1, false) && activeTracking && trackingTime(activeTracking.locked_from) && trackingTime(activeTracking.last_confirmed, true);
    const blocked = trackingSaveBlocked();
    const entry = entries.find(function (item) { return item.date === selectedDate; });
    const supplementBlocked = Boolean(live && entry && entry.kind === "intervals_override" && form.elements.kind.value === "intervals");
    const unavailable = Boolean(currentTimeChoice(selectedDate, today, timezone, 0, 1, false) && trackingStatusUnavailable);
    const expired = Boolean(selectedDate === today && today && !currentTimeChoice(selectedDate, today, timezone, 0, 1, false) && dirty());
    if (expired) freezeConflictDraft();
    if (!live && !blocked && !unavailable && !expired) { box.replaceChildren(); box.hidden = true; return; }
    box.hidden = false;
    if (live) {
      let details = box.querySelector(".manual-active-card");
      if (!details) {
        details = element("details", "manual-active-card");
        const summary = element("summary", "manual-active-summary");
        summary.append(element("span", "manual-active-title", loc("正在自动记录 · 暂不可修正")), element("span", "manual-active-time"), element("span", "manual-active-help", "ⓘ"));
        summary.title = loc("此时段正在自动记录，暂时不能修正；结束后重新打开即可修改。");
        details.append(summary, element("p", "manual-active-tooltip"));
        box.prepend(details);
      }
      const locked = trackingTime(activeTracking.locked_from);
      details.querySelector("summary").title = loc("此时段正在自动记录，暂时不能修正；结束后重新打开即可修改。");
      details.querySelector(".manual-active-title").textContent = loc("第 ") + ($("manual-interval-rows").children.length + 1) + loc(" 段 · 正在自动记录 · 暂不可修正");
      details.querySelector(".manual-active-time").textContent = loc("保护范围 ") + locked + loc(" – 至今");
      const explanation = loc("从 ") + locked + loc(" 起保留自动记录（最近确认 ") + trackingTime(activeTracking.last_confirmed, true) + loc("），此段暂时不能修正；连接结束后重新打开即可修改。起点按分钟向前取整保护。");
      details.querySelector(".manual-active-tooltip").textContent = explanation;
    } else {
      const details = box.querySelector(".manual-active-card"); if (details) details.remove();
    }
    const message = presentTrackingConflict ? loc("自动记录状态已变化。为保留草稿，请先记录当前修改，再重新打开工作历史；未保存的内容不会自动写入。") : blocked ? (activeTracking && activeTracking.message) || (dayData && dayData.active_tracking && dayData.active_tracking.message) || loc("自动记录状态已变化；为保护当前时段，请重新打开工作历史再修改。") : supplementBlocked ? loc("当前连接仍在记录，请切回修正；若要使用补充，请先撤销当天修正。") : unavailable ? loc("暂时无法刷新自动记录状态；当前草稿的修正范围不会变化。") : "";
    let warning = box.querySelector(".manual-active-warning");
    if (message) {
      if (!warning) { warning = element("p", "manual-active-warning"); box.append(warning); }
      warning.textContent = loc(message);
    } else if (warning) warning.remove();
    let backup = box.querySelector(".manual-conflict-backup");
    if ((presentTrackingConflict || expired) && conflictSnapshot && !privacyHidden()) {
      if (!backup) {
        backup = element("details", "manual-conflict-backup");
        backup.append(element("summary", "", loc("查看状态变化前的草稿")));
        const description = element("p", "field-hint", loc("这是状态变化时的快照，可选中复制；当前编辑内容仍保留在下方。"));
        const field = element("textarea"); field.readOnly = true; field.rows = 5;
        field.setAttribute("aria-label", loc("状态变化前的草稿快照"));
        backup.append(description, field); box.append(backup);
      }
      const value = conflictSnapshot.value;
      backup.querySelector("summary").textContent = loc("查看状态变化前的草稿");
      backup.querySelector("p").textContent = loc("这是状态变化时的快照，可选中复制；当前编辑内容仍保留在下方。");
      backup.querySelector("textarea").setAttribute("aria-label", loc("状态变化前的草稿快照"));
      const lines = [value.date, value.kind === "daily_total" ? loc("按总小时记录：") + value.hours : loc("工作时段：")];
      if (value.intervals) value.intervals.forEach(function (span, index) {
        lines.push(loc("第 ") + (index + 1) + loc(" 段：") + span.start + "–" + span.end +
          (conflictSnapshot.present && index === value.intervals.length - 1 ? loc("（当时的至今）") : ""));
      });
      if (value.note && !numbersHidden()) lines.push(loc("备注：") + value.note);
      backup.querySelector("textarea").value = lines.join("\n");
    } else if (backup) backup.remove();
  }
  async function refreshActiveTracking() {
    if (!dialog.open || selectedDate !== today || dayLoading || trackingRefreshPending) return;
    if (!currentTimeChoice(selectedDate, today, timezone, 0, 1, false)) {
      activeTracking = null; trackingStatusUnavailable = false; updateFields(); return;
    }
    const date = selectedDate, sequence = dayRequest;
    trackingRefreshPending = true;
    try {
      const result = await request("/api/history-day?date=" + encodeURIComponent(date));
      if (!dialog.open || sequence !== dayRequest || date !== selectedDate) return;
      const nextActive = result.active_tracking || null;
      if (Boolean(nextActive) !== Boolean(activeTracking)) {
        if (dirty()) {
          // Do not reinterpret an in-progress manual draft as a different
          // protected range when collection starts or stops.
          freezeConflictDraft(); presentTrackingConflict = true;
        } else {
          activeTracking = nextActive;
          trackingStatusUnavailable = false;
          loadDate(date, true);
          return;
        }
      }
      activeTracking = nextActive;
      trackingStatusUnavailable = false;
    } catch (_) {
      if (!dialog.open || sequence !== dayRequest || date !== selectedDate) return;
      if (activeTracking) {
        if (dirty()) {
          freezeConflictDraft(); presentTrackingConflict = true;
        } else {
          activeTracking = null;
          trackingStatusUnavailable = true;
          bindPresentRow();
          baseline = fingerprint();
        }
      }
      trackingStatusUnavailable = true;
    } finally {
      trackingRefreshPending = false;
      if (dialog.open && sequence === dayRequest && date === selectedDate) updateFields();
    }
  }
  window.setInterval(refreshActiveTracking, 15000);
  async function loadDayDetails(date) {
    const sequence = ++dayRequest, panel = $("history-segments"); dayData = null; activeTracking = null; trackingStatusUnavailable = false;
    panel.replaceChildren(element("p", "field-hint", loc("正在读取当天分段…")));
    try {
      const result = await request("/api/history-day?date=" + encodeURIComponent(date));
      if (sequence !== dayRequest || date !== selectedDate) return;
      const pristine = !dirty();
      dayData = result; activeTracking = result.active_tracking || null; panel.replaceChildren();
      // Existing protected tails are not editable in this snapshot; never
      // project the preceding editable row across their gaps up to now.
      if (pristine && Array.isArray(result.protected_tail_intervals) && result.protected_tail_intervals.length) {
        presentClosed = true; baseline = fingerprint();
      }
      // The user may have typed while the day details were loading. Do not
      // reinterpret that existing draft's last end under the newly learned
      // tracking state without giving them a chance to preserve it.
      if (!pristine && date === today && !activeTracking && rows().length && !presentRow) { freezeConflictDraft(); presentTrackingConflict = true; }
      const existing = entries.find(function (entry) { return entry.date === date; });
      if (date === today && result.today_override_available === false && !dirty() && form.elements.kind.value === "intervals_override") {
        form.elements.kind.value = "intervals";
        baseline = fingerprint();
      }
      const prefilled = shouldPrefillIntervals(existing, date, today) && !dirty() && form.elements.kind.value === "intervals_override" && Array.isArray(result.editable_intervals) && result.editable_intervals.length > 0;
      if (prefilled) {
        renderIntervals(result.editable_intervals);
        baseline = fingerprint();
      } else if (pristine) {
        bindPresentRow();
        baseline = fingerprint();
      }
      dayWasPrefilled = prefilled; renderDayPanel(date, result, prefilled);
      return true;
    } catch (error) {
      if (sequence === dayRequest && date === selectedDate) panel.replaceChildren(element("p", "form-error", loc("无法读取当天分段：") + error.message));
      return false;
    } finally {
      if (sequence === dayRequest && date === selectedDate) { dayLoading = false; updateFields(); }
    }
  }
  function renderDayPanel(date, result, prefilled) {
    const panel = $("history-segments");
    const expanded = Array.from(panel.querySelectorAll("details")).map(function (item) { return item.open; });
    panel.replaceChildren();
  panel.append(element("h4", "", loc("当天记录分段")));
  panel.append(element("p", "field-hint", result.manual_entry && result.manual_entry.kind === "daily_total" ? loc("当天按手动总小时估算，以下采样分段不能代表该估算的具体时间。时间为 ") + timezone + loc("。") : loc("以下是实际采样与手动记录计算后的分段；未确认状态不会算作已连接。时间为 ") + timezone + loc("。")));
  const names = { connected: loc("已连接"), disconnected: loc("已断开"), unknown: loc("未知") };
  const sources = { vpn: "VPN", manual: loc("手动"), manual_override: loc("手动修正"), manual_paused: loc("手动暂停"), night_paused: loc("夜间暂停"), sleep_estimate: loc("睡眠估算"), sleep_paused: loc("睡眠暂停"), sleep_unknown: loc("睡眠未知") };
  if (!Array.isArray(result.segments) || !result.segments.length) panel.append(element("p", "field-hint", loc("没有可展示的具体时段；按总小时估算的记录不会虚构分段。")));
  else {
    const list = element("ul", "history-segment-list");
    result.segments.forEach(function (segment) {
      const row = element("li"), time = element("span", "history-segment-time", segmentTime(segment.start, date) + "–" + segmentTime(segment.end, date));
      const state = segment.source === "manual_override" ? (segment.state === "connected" ? loc("已计入") : loc("未计入")) : segment.source === "sleep_paused" || segment.source === "night_paused" || segment.source === "manual_paused" ? loc("未计入") : segment.source === "sleep_estimate" ? loc("已计入") : names[segment.state] || segment.state || loc("未知");
      row.append(time, element("span", "", (sources[segment.source] || segment.source || loc("记录")) + " · " + state));
      list.append(row);
    });
    panel.append(list);
  }
  if (Array.isArray(result.protected_tail_intervals) && result.protected_tail_intervals.length) {
    const tails = element("p", "field-hint history-protected-tail");
    tails.textContent = loc("已保存的截止后手动工作：") + result.protected_tail_intervals.map(function (span) {
      return span.start + "–" + span.end;
    }).join(loc("、")) + loc("。这些时段会保留；如需修改，可撤销当天修正，或在次日编辑完整记录。");
    panel.append(tails);
  }
  if (Array.isArray(result.raw_segments) && result.raw_segments.length) {
    const details = element("details", "history-raw-segments"), summary = element("summary", "", loc("查看原始 VPN 状态")), rawList = element("ul", "history-segment-list");
    result.raw_segments.forEach(function (segment) {
      const row = element("li");
      row.append(element("span", "history-segment-time", segmentTime(segment.start, date) + "–" + segmentTime(segment.end, date)), element("span", "", names[segment.state] || segment.state || loc("未知"))); rawList.append(row);
    });
    details.append(summary, rawList); panel.append(details);
  }
  if (result.manual_entry && result.manual_entry.kind === "intervals_override") {
    const restore = element("button", "secondary-button history-restore", loc("撤销当天修正")); restore.type = "button"; restore.disabled = busy;
    restore.addEventListener("click", async function () {
      if (busy || date !== selectedDate || !discardDraft() || !window.confirm(loc("撤销当天修正并恢复修正前的记录？原始 VPN 采样不受影响。"))) return;
      showError(""); setBusy(true);
      try { const result = await request("/api/manual-entries/delete", { date: date }); await afterManualChange(result, loc("已撤销当天修正")); }
      catch (error) { showError(error.message); }
      finally { setBusy(false); }
    });
    panel.append(restore);
  }
  if (date <= today && Array.isArray(result.editable_intervals) && result.editable_intervals.length) {
    const button = element("button", "secondary-button history-copy-segments", loc("用当天已计时段作为修正起点")); button.type = "button"; button.disabled = busy;
    button.addEventListener("click", function () {
      if (busy || date !== selectedDate || !dayData || !discardDraft()) return;
      form.elements.kind.value = "intervals_override";
      renderIntervals(dayData.editable_intervals); showError(""); updateFields();
    });
    panel.append(button, element("p", "field-hint history-edit-snapshot-hint", (prefilled ? loc("已将当天已计时段填入编辑器。") : loc("可将当天已计时段填入编辑器。")) + loc("自动采样精确到秒，填入时按分钟取整；请核对并调整后保存。") + (date === today ? loc("修正截至 ") + cutoffTime(result.edit_cutoff) + loc("，其后继续自动记录；重新打开可刷新截止时间。") : loc("保存后仅修正时段计工时，其余时间（包括未知时间）均不计入。")) + loc("原始 VPN 记录保留，可撤销恢复。")));
  } else if (result.editable_reason) panel.append(element("p", "field-hint", loc(result.editable_reason)));
  else if (date === today) panel.append(element("p", "field-hint history-edit-snapshot-hint", loc("今天的修正截至 ") + cutoffTime(result.edit_cutoff) + loc("，其后继续自动记录；重新打开可刷新截止时间。")));
    Array.from(panel.querySelectorAll("details")).forEach(function (item, index) { if (expanded[index]) item.open = true; });
  }
  function showError(message) { $("manual-error").textContent = loc(message); $("manual-error").hidden = !message; }
  function confirmManualTail(start, end, limit) {
    return new Promise(function (resolve) {
      const prompt = element("dialog", "manual-tail-confirm");
      prompt.setAttribute("aria-label", loc("确认手动工作时间"));
      prompt.append(element("h3", "", loc("确认手动工作时间")));
      prompt.append(element("p", "", loc("修正范围截至 ") + limit + loc("。")));
      prompt.append(element("p", "", start + "–" + end + loc(" 将作为你手动填写的工作时间计入。原始记录、未填写的未知时间和之后的自动记录会保留。")));
      const actions = element("div", "manual-tail-confirm-actions");
      const cancel = element("button", "secondary-button", loc("继续编辑")); cancel.type = "button";
      const accept = element("button", "primary-button", loc("确认保存")); accept.type = "button";
      cancel.addEventListener("click", function () { prompt.close("cancel"); });
      accept.addEventListener("click", function () { prompt.close("accept"); });
      actions.append(cancel, accept); prompt.append(actions); document.body.append(prompt);
      prompt.addEventListener("close", function () { const accepted = prompt.returnValue === "accept"; prompt.remove(); resolve(accepted); }, { once: true });
      prompt.addEventListener("cancel", function (event) { event.preventDefault(); prompt.close("cancel"); });
      try { prompt.showModal(); cancel.focus(); }
      catch (_) { prompt.remove(); resolve(false); }
    });
  }
  function rows() {
    return Array.from($("manual-interval-rows").children).map(function (row) {
      return { start: row.querySelector('[data-part="start-hour"]').value + ":" + row.querySelector('[data-part="start-minute"]').value,
        end: row.querySelector('[data-part="end-hour"]').value + ":" + row.querySelector('[data-part="end-minute"]').value };
    });
  }
  function draft() {
    const value = { date: selectedDate, kind: form.elements.kind.value, note: form.elements.note.value, presentClosed: presentClosed };
    if (value.kind === "daily_total") value.hours = form.elements.hours.value;
    else value.intervals = rows();
    return value;
  }
  function freezeConflictDraft() {
    if (!conflictSnapshot) conflictSnapshot = { value: JSON.parse(JSON.stringify(draft())), present: Boolean(presentRow) };
  }
  function undoState() {
    return { date: selectedDate, kind: form.elements.kind.value, intervals: rows(), present: Boolean(presentRow),
      active: Boolean(activeTracking), cutoff: dayData && dayData.edit_cutoff, revision: dayData && dayData.edit_revision,
      rebasePending: rebasePending, presentClosed: presentClosed };
  }
  function recordUndo(before, group) { undo.record(before, undoState(), group); }
  function fingerprint() { return draftFingerprint(draft(), Boolean(presentRow)); }
  function dirty() { return Boolean(baseline && (rebasePending || fingerprint() !== baseline)); }
  function discardDraft() { return !dirty() || window.confirm(loc("这一天有尚未保存的修改。放弃这些修改并继续？")); }
  function previousEntry() {
    return entries.filter(function (entry) { return entry.date < selectedDate && (selectedDate !== today || entry.kind === "intervals"); })
      .sort(function (a, b) { return b.date.localeCompare(a.date); })[0];
  }
  function setBusy(value) { busy = value; updateFields(); renderCalendar(); }
  const editorModes = element("div", "interval-editor-modes");
  const refreshRange = element("button", "secondary-button manual-refresh-range", loc("更新可修正范围"));
  refreshRange.type = "button"; refreshRange.hidden = true;
  refreshRange.title = loc("保留草稿，检查最新记录并在确认后更新截止时间");
  $("manual-date-hint").after(refreshRange);
  editorModes.setAttribute("role", "group"); editorModes.setAttribute("aria-label", loc("工作时段编辑方式"));
  const timelineMode = element("button", "secondary-button", loc("滑动时间轴")); timelineMode.type = "button";
  const preciseMode = element("button", "secondary-button", loc("精确选择时间")); preciseMode.type = "button";
  editorModes.append(timelineMode, preciseMode);
  $("manual-interval-rows").before(editorModes);
  const undoButton = element("button", "secondary-button manual-undo", loc("撤销上一步"));
  undoButton.type = "button"; undoButton.title = undoAvailable ? loc("撤销本次编辑中的上一个时段操作") : loc("请重启本机服务后使用撤销");
  editorModes.after(undoButton);
  undoButton.addEventListener("click", function () {
    const previous = undo.peek(selectedDate);
    if (busy || privacyHidden() || !previous) return;
    if (presentTrackingConflict || trackingStatusUnavailable || previous.kind !== form.elements.kind.value ||
        previous.active !== Boolean(activeTracking) || previous.cutoff !== (dayData && dayData.edit_cutoff) ||
        previous.revision !== (dayData && dayData.edit_revision) ||
        (previous.present && !currentTimeChoice(selectedDate, today, timezone, 0, 1, false))) {
      showError(loc("自动记录或修正范围已变化，无法安全撤销；当前草稿和撤销记录仍在。")); return;
    }
    const limit = editLimit();
    if (activeTracking && previous.intervals.some(function (span) { return minute(span.end, true) > limit; })) {
      showError(loc("该步骤与正在自动记录的时段重叠，暂时不能撤销；当前草稿仍在。")); return;
    }
    presentClosed = Boolean(previous.presentClosed); renderIntervals(previous.intervals, true); rebasePending = previous.rebasePending;
    undo.discard(selectedDate); showError(""); statusMessage(loc("已撤销上一步，修改尚未保存。")); updateFields();
  });
  document.addEventListener("pointerup", function () { if (dragGroup !== null) { dragGroup = null; undo.endGroup(); } });
  document.addEventListener("pointercancel", function () { if (dragGroup !== null) { dragGroup = null; undo.endGroup(); } });
  const activeTrackingBox = element("div", "manual-active-tracking"); activeTrackingBox.id = "manual-active-tracking"; activeTrackingBox.hidden = true;
  $("manual-interval-rows").after(activeTrackingBox);
  const closedPresent = element("p", "field-hint manual-closed-present", loc("至今 · 之后无新增手动工作，自动计时仍按当前状态运行"));
  closedPresent.hidden = true; activeTrackingBox.before(closedPresent);
  function setEditorMode(mode) {
    intervalEditor = mode;
    timelineMode.setAttribute("aria-pressed", String(mode === "timeline"));
    preciseMode.setAttribute("aria-pressed", String(mode === "precise"));
    $("manual-interval-rows").querySelectorAll(".manual-interval-row").forEach(syncIntervalRow);
  }
  timelineMode.addEventListener("click", function () { setEditorMode("timeline"); });
  preciseMode.addEventListener("click", function () { setEditorMode("precise"); });
  setEditorMode("timeline");
  function editLimit() {
    const current = currentTimeChoice(selectedDate, today, timezone, 0, 1, false);
    if (!current) return 1440;
    let limit = minute(current, false);
    const locked = activeTracking && trackingTime(activeTracking.locked_from);
    if (locked) limit = Math.min(limit, minute(locked, false));
    if (dayData && Array.isArray(dayData.protected_tail_intervals) && dayData.protected_tail_intervals.length) {
      const cutoff = cutoffTime(dayData.edit_cutoff);
      if (cutoff) limit = Math.min(limit, minute(cutoff, false));
    }
    return limit;
  }
  function syncIntervalRow(row) {
    const pair = row.querySelector(".manual-time-pair"), editor = row.querySelector(".interval-slider");
    pair.hidden = intervalEditor !== "precise"; editor.hidden = intervalEditor !== "timeline";
    const startText = row.querySelector('[data-part="start-hour"]').value + ":" + row.querySelector('[data-part="start-minute"]').value;
    const endText = row.querySelector('[data-part="end-hour"]').value + ":" + row.querySelector('[data-part="end-minute"]').value;
    let start, end;
    try { start = minute(startText, false); end = minute(endText, true); } catch (_) { return; }
    const all = Array.from($("manual-interval-rows").children), index = all.indexOf(row);
    const ordinal = index + 1;
    row.querySelector(".manual-interval-row-header > span").textContent = loc("第 ") + ordinal + loc(" 段");
    const splitLabel = row.querySelector(".manual-split-interval"), mergeLabel = row.querySelector(".manual-merge-interval"), removeLabel = row.querySelector(".manual-remove-interval");
    splitLabel.textContent = loc("拆分"); splitLabel.setAttribute("aria-label", loc("拆分第 ") + ordinal + loc(" 段工作"));
    mergeLabel.textContent = loc("与下一段合并"); mergeLabel.setAttribute("aria-label", loc("将第 ") + ordinal + loc(" 段与下一段合并"));
    removeLabel.textContent = loc("移除"); removeLabel.setAttribute("aria-label", loc("移除第 ") + ordinal + loc(" 段工作"));
    ["start", "end"].forEach(function (side, position) {
      const label = side === "start" ? loc("开始") : loc("结束");
      const group = pair.children[position];
      if (group && group.firstChild) group.firstChild.nodeValue = label;
      ["hour", "minute"].forEach(function (unit) {
        row.querySelector('[data-part="' + side + '-' + unit + '"]').setAttribute("aria-label", loc("第 ") + ordinal + loc(" 段") + label + (unit === "hour" ? loc("小时") : loc("分钟")));
      });
      row.querySelector('[data-slider="' + side + '"]').setAttribute("aria-label", loc("第 ") + ordinal + loc(" 段") + (side === "start" ? loc("开始时间") : loc("结束时间")));
    });
    row.querySelector(".manual-end-present span").textContent = loc("结束");
    row.querySelector(".manual-present-label").textContent = loc("至今");
    const bounds = intervalWindow(rows(), index, editLimit());
    const startSlider = row.querySelector('[data-slider="start"]'), endSlider = row.querySelector('[data-slider="end"]');
    [startSlider, endSlider].forEach(function (slider) { slider.min = bounds.min; slider.max = bounds.max; slider.step = 1; });
    startSlider.value = start; endSlider.value = end;
    row.dataset.start = startText; row.dataset.end = endText;
    // A collection-state change while editing freezes the original draft.
    // Show the final row as present without changing its saved end; the
    // warning blocks saving until the user can reconcile the snapshot.
    const conflictPresent = presentTrackingConflict && (!activeTracking || trackingStatusUnavailable) && row === $("manual-interval-rows").lastElementChild;
    const projectedPresent = row === presentRow && !(presentTrackingConflict && activeTracking && !trackingStatusUnavailable);
    const isPresent = (projectedPresent || conflictPresent) && Boolean(currentTimeChoice(selectedDate, today, timezone, 0, 1, false));
    endSlider.disabled = busy || isPresent || row === presentRow;
    startSlider.setAttribute("aria-valuetext", startText); endSlider.setAttribute("aria-valuetext", isPresent ? loc("至今") : endText);
    row.querySelector(".interval-slider-values").textContent = startText + " — " + (isPresent ? loc("至今") : endText);
    row.querySelector(".manual-end-fixed").hidden = isPresent;
    row.querySelector(".manual-end-present").hidden = !isPresent;
    row.querySelector(".manual-present-hint").hidden = !isPresent;
    row.querySelector(".manual-present-hint").textContent = conflictPresent ? loc("自动记录状态已变化。草稿中这一段的原结束时间为 ") + endText + loc("；请先记下草稿再重新打开工作历史。") : loc("手动预览随时间更新；保存时截止当下，之后由自动计时决定。");
    row.querySelector(".interval-slider-hint").textContent = isPresent ? loc("拖动开始时间；结束时间为至今。") : loc("拖动两端或用方向键按分钟调整，点击轨道可定位。");
    const info = row.querySelector(".interval-window-hint");
    info.textContent = bounds.conflict ? loc("时段有重叠、顺序不对或超出可调整范围，请调整或移除后再保存。") : loc("可调整范围 ") + clock(bounds.min) + "–" + clock(bounds.max) + loc("；不会越过相邻时段。");
    info.classList.toggle("is-conflict", bounds.conflict);
    if (bounds.conflict) info.setAttribute("role", "alert"); else info.removeAttribute("role");
    row.querySelectorAll(".interval-slider-ticks span").forEach(function (tick, i) { tick.textContent = clock(Math.round(bounds.min + (bounds.max - bounds.min) * i / 4)); });
    const fill = row.querySelector(".interval-slider-fill");
    const width = bounds.max - bounds.min;
    const startRatio = (start - bounds.min) / width, spanRatio = Math.max(0, end - start) / width;
    // Native range thumbs travel between their centres, inset by half the
    // 28px thumb width at either end of the input.
    fill.style.left = "calc(" + (startRatio * 100) + "% + 14px - " + (28 * startRatio) + "px)";
    fill.style.width = "calc(" + (spanRatio * 100) + "% - " + (28 * spanRatio) + "px)";
    editor.classList.toggle("is-close", (end - start) / width <= 0.08);
  }
  function applySlider(row, side, value) {
    if (busy) return;
    if (side === "end" && (row === presentRow || presentTrackingConflict && (!activeTracking || trackingStatusUnavailable) && row === $("manual-interval-rows").lastElementChild)) return;
    const all = Array.from($("manual-interval-rows").children), index = all.indexOf(row), values = rows(), before = undoState();
    // Dropdown change fires after its value changed. Keep the previous row as
    // the constraint reference so moving into a neighbour cannot bypass it.
    if (row.dataset.start && row.dataset.end) {
      values[index] = { start: row.dataset.start, end: row.dataset.end };
      before.intervals[index] = { start: row.dataset.start, end: row.dataset.end };
    }
    const adjusted = adjustIntervalBoundary(values, index, side, value, editLimit());
    ["start", "end"].forEach(function (part, index) {
      const selected = clock(adjusted[index]).split(":");
      row.querySelector('[data-part="' + part + '-hour"]').value = selected[0];
      row.querySelector('[data-part="' + part + '-minute"]').value = selected[1];
    });
    recordUndo(before, dragGroup); showError(""); updateFields();
  }
  function updateFields() {
    bindPresentRow();
    const daily = form.elements.kind.value === "daily_total";
    form.querySelectorAll("input,select,button").forEach(function (control) { control.disabled = busy; });
    form.elements.kind.querySelector('[value="daily_total"]').disabled = selectedDate === today;
    form.elements.kind.querySelector('[value="intervals_override"]').disabled = selectedDate === today && dayData && dayData.today_override_available === false;
    const existingForType = entries.find(function (entry) { return entry.date === selectedDate; });
    form.elements.kind.querySelector('[value="intervals"]').disabled = Boolean(selectedDate === today && activeTracking && existingForType && existingForType.kind === "intervals_override");
    refreshRange.hidden = daily || form.elements.kind.value !== "intervals_override" || !currentTimeChoice(selectedDate, today, timezone, 0, 1, privacyHidden());
    refreshRange.disabled = busy || dayLoading || !dayData || !Number.isFinite(dayData.edit_cutoff);
    $("manual-hours-field").hidden = !daily; $("manual-intervals-field").hidden = daily;
    form.elements.hours.disabled = busy || !daily; form.elements.hours.required = daily;
    $("manual-interval-rows").querySelectorAll("select").forEach(function (control) { control.disabled = busy || daily; });
    const intervalRows = $("manual-interval-rows").querySelectorAll(".manual-interval-row");
    intervalRows.forEach(function (row, index) {
      const endMinute = row.querySelector('[data-part="end-minute"]');
      if (row.querySelector('[data-part="end-hour"]').value === "24") { endMinute.value = "00"; endMinute.disabled = true; }
      const split = row.querySelector(".manual-split-interval"), merge = row.querySelector(".manual-merge-interval");
      let canSplit = false;
      try { canSplit = minute(row.querySelector('[data-part="end-hour"]').value + ":" + endMinute.value, true) - minute(row.querySelector('[data-part="start-hour"]').value + ":" + row.querySelector('[data-part="start-minute"]').value, false) >= 2; } catch (_) {}
      split.disabled = busy || daily || intervalRows.length >= 12 || !canSplit;
      split.title = intervalRows.length >= 12 ? loc("每天最多 12 段") : !canSplit ? loc("至少 2 分钟才能拆分") : loc("先从中点拆分，之后可调整时间");
      merge.disabled = busy || daily || index === intervalRows.length - 1;
      syncIntervalRow(row);
    });
    form.elements.date.max = today;
    const existing = entries.some(function (entry) { return entry.date === selectedDate; });
    $("save-manual").textContent = existing ? loc("保存修改") : loc("保存手动记录");
    $("manual-add-interval").disabled = busy || $("manual-interval-rows").children.length >= 12;
    undoButton.disabled = busy || privacyHidden() || !undo.peek(selectedDate);
    closedPresent.hidden = !presentClosed || selectedDate !== today || Boolean(activeTracking) || form.elements.kind.value === "daily_total" || !currentTimeChoice(selectedDate, today, timezone, 0, 1, false);
    const expiredToday = selectedDate === today && today && !currentTimeChoice(selectedDate, today, timezone, 0, 1, false);
    $("manual-date-hint").textContent = expiredToday ? loc("日期已变化，原来的今日修正范围不能再保存。草稿仍在，请先记录内容再重新打开工作历史。") : loc("按 ") + (timezone || loc("本机时区")) + loc(" 计算。") + (existing ? loc("已加载当天记录，可直接修改。") : "") + (form.elements.kind.value === "intervals_override" ? (selectedDate === today ? loc("修正截至 ") + (cutoffTime(dayData && dayData.edit_cutoff) || loc("加载中")) + loc("，其后继续自动记录。") : loc("修正后仅所填时段计工时，其余时间（包括未知时间）不计入。")) + loc("原始 VPN 记录保留。") : selectedDate === today ? loc("今天只记录已经经过的部分。") : "");
    const previous = previousEntry();
    $("manual-copy-previous").disabled = busy || !previous;
    $("manual-copy-previous").textContent = previous ? loc("沿用 ") + previous.date.replaceAll("-", "/") + loc(" 的手动记录") : loc("还没有可沿用的更早手动记录");
    $("manual-prev-month").disabled = busy || !calendarMonth || calendarMonth <= "0001-01";
    $("manual-next-month").disabled = busy || !calendarMonth || calendarMonth >= today.slice(0, 7);
    $("manual-calendar-days").querySelectorAll("button").forEach(function (button) { button.disabled = busy || button.dataset.date > today; });
    renderActiveTracking(); updatePreview();
  }
  function timeSelect(part, limit, selected, label) {
    const select = element("select"); select.dataset.part = part; select.setAttribute("aria-label", label);
    for (let i = 0; i <= limit; i++) {
      const value = String(i).padStart(2, "0"), option = element("option", "", value);
      option.value = value; select.append(option);
    }
    select.value = selected;
    select.addEventListener("change", function () {
      const row = select.closest(".manual-interval-row"), side = part.indexOf("start-") === 0 ? "start" : "end";
      const hour = row.querySelector('[data-part="' + side + '-hour"]'), mins = row.querySelector('[data-part="' + side + '-minute"]');
      if (side === "end" && hour.value === "24") mins.value = "00";
      try { applySlider(row, side, minute(hour.value + ":" + mins.value, side === "end")); }
      catch (error) { showError(error.message); updateFields(); }
    });
    return select;
  }
  function bindPresentRow() {
    const all = Array.from($("manual-interval-rows").children);
    if (presentTrackingConflict) {
      if (presentRow && !all.includes(presentRow)) presentRow = null;
      return;
    }
    if (presentClosed) { presentRow = null; return; }
    const index = dayData && form.elements.kind.value !== "daily_total" ?
      defaultPresentIndex(selectedDate, today, timezone, all.length, activeTracking, trackingStatusUnavailable) : -1;
    presentRow = index < 0 ? null : all[index];
    if (presentRow && !busy) updatePresent(false);
  }
  function updatePresent(strict) {
    if (!presentRow) return true;
    const all = Array.from($("manual-interval-rows").children), position = all.indexOf(presentRow);
    const start = presentRow.querySelector('[data-part="start-hour"]').value + ":" + presentRow.querySelector('[data-part="start-minute"]').value;
    const value = currentTimeChoice(selectedDate, today, timezone, position, all.length, false);
    if (!value) {
      if (strict) throw new Error(loc("日期已变化，不能保存之前的至今时段；草稿仍在。请先记录内容再重新打开工作历史。"));
      return false;
    }
    const pieces = value.split(":");
    presentRow.querySelector('[data-part="end-hour"]').value = pieces[0];
    presentRow.querySelector('[data-part="end-minute"]').value = pieces[1];
    if (minute(value, false) <= minute(start, false)) {
      if (strict) throw new Error(loc("至今须晚于这一段的开始时间；请调整开始时间。"));
      return false;
    }
    return true;
  }
  window.setInterval(function () {
    if (!presentRow || !dialog.open || busy || privacyHidden() || presentTrackingConflict) return;
    updatePresent(false); updateFields();
  }, 15000);
  function appendInterval(interval) {
    const index = $("manual-interval-rows").children.length + 1;
    const row = element("div", "manual-interval-row"), heading = element("div", "manual-interval-row-header");
    heading.append(element("span", "", loc("第 ") + index + loc(" 段")));
    const actions = element("div", "manual-interval-actions");
    const split = element("button", "manual-split-interval", loc("拆分")); split.type = "button";
    split.setAttribute("aria-label", loc("拆分第 ") + index + loc(" 段工作"));
    split.addEventListener("click", function () {
      if (busy) return;
      try {
        const values = rows(), position = Array.from($("manual-interval-rows").children).indexOf(row), before = undoState();
        renderIntervals(splitInterval(values, position), true); recordUndo(before); showError(""); updateFields();
      } catch (error) { showError(error.message); }
    });
    const merge = element("button", "manual-merge-interval", loc("与下一段合并")); merge.type = "button";
    merge.setAttribute("aria-label", loc("将第 ") + index + loc(" 段与下一段合并"));
    merge.addEventListener("click", function () {
      if (busy) return;
      try {
        const values = rows(), position = Array.from($("manual-interval-rows").children).indexOf(row), result = mergeIntervals(values, position), before = undoState();
        if (result.gap && !window.confirm(loc("合并后两段之间的 ") + result.gap + loc(" 分钟也会计入工时，本次填写的总工时将增加 ") + result.added + loc(" 分钟。确定合并吗？"))) return;
        renderIntervals(result.intervals, true); recordUndo(before); showError(""); updateFields();
      } catch (error) { showError(error.message); }
    });
    const remove = element("button", "manual-remove-interval", loc("移除")); remove.type = "button";
    remove.setAttribute("aria-label", loc("移除第 ") + index + loc(" 段工作"));
    remove.addEventListener("click", function () {
      if (busy) return;
      const values = rows(), position = Array.from($("manual-interval-rows").children).indexOf(row), before = undoState();
      if (row === presentRow) presentClosed = true;
      values.splice(position, 1);
      if (row === presentRow) presentRow = null;
      renderIntervals(values, true); recordUndo(before); updateFields();
    });
    const presentHint = element("p", "manual-present-hint", loc("手动预览随时间更新；保存时截止当下，之后由自动计时决定。"));
    presentHint.hidden = true;
    actions.append(split, merge, remove); heading.append(actions); row.append(heading, presentHint);
    const pair = element("div", "manual-time-pair");
    ["start", "end"].forEach(function (side) {
      const label = side === "start" ? loc("开始") : loc("结束"), group = element("div", "manual-time-label", label);
      if (side === "end") group.classList.add("manual-end-fixed");
      const selects = element("div", "manual-time-selects"), value = interval[side].split(":");
      selects.append(timeSelect(side + "-hour", side === "end" ? 24 : 23, value[0], loc("第 ") + index + loc(" 段") + label + loc("小时")), element("span", "", ":"),
        timeSelect(side + "-minute", 59, value[1], loc("第 ") + index + loc(" 段") + label + loc("分钟")));
      group.append(selects); pair.append(group);
    });
    const presentEnd = element("div", "manual-time-label manual-end-present");
    presentEnd.append(element("span", "", loc("结束")), element("strong", "manual-present-label", loc("至今")));
    presentEnd.hidden = true; pair.append(presentEnd);
    row.append(pair);
    const editor = element("div", "interval-slider"), values = element("div", "interval-slider-values");
    const rail = element("div", "interval-slider-rail"), fill = element("span", "interval-slider-fill"); rail.append(fill);
    ["start", "end"].forEach(function (side) {
      const slider = element("input", "interval-slider-handle interval-slider-" + side);
      slider.type = "range"; slider.min = "0"; slider.max = side === "start" ? "1439" : "1440"; slider.step = "1"; slider.dataset.slider = side;
      slider.setAttribute("aria-label", loc("第 ") + index + loc(" 段") + (side === "start" ? loc("开始时间") : loc("结束时间")));
      slider.addEventListener("pointerdown", function () { dragGroup = ++dragSequence; });
      slider.addEventListener("input", function () { applySlider(row, side, Number(slider.value)); }); rail.append(slider);
    });
    rail.addEventListener("pointerdown", function (event) {
      if (busy || event.target !== rail && event.target !== fill) return;
      const bounds = rail.getBoundingClientRect(), slider = row.querySelector('[data-slider="start"]');
      const inset = 14, usableWidth = bounds.width - 2 * inset;
      if (usableWidth <= 0) return;
      const min = Number(slider.min), max = Number(slider.max);
      const value = Math.round(min + Math.max(0, Math.min(1, (event.clientX - bounds.left - inset) / usableWidth)) * (max - min));
      const start = Number(slider.value), end = Number(row.querySelector('[data-slider="end"]').value);
      const side = row === presentRow || Math.abs(value - start) <= Math.abs(value - end) ? "start" : "end";
      applySlider(row, side, value);
    });
    const ticks = element("div", "interval-slider-ticks"); for (let tick = 0; tick < 5; tick++) ticks.append(element("span", "", ""));
    const windowHint = element("p", "interval-window-hint"); windowHint.setAttribute("aria-live", "polite");
    editor.append(values, rail, ticks, element("p", "interval-slider-hint", loc("拖动两端或用方向键按分钟调整。")), windowHint);
    row.append(editor); $("manual-interval-rows").append(row); syncIntervalRow(row);
  }
  function renderIntervals(values, keepPresent) {
    presentRow = null;
    $("manual-interval-rows").replaceChildren(); values.forEach(appendInterval);
    bindPresentRow();
    $("manual-interval-rows").querySelectorAll(".manual-interval-row").forEach(syncIntervalRow);
  }
  function loadDate(value, force) {
    if (!validDate(value) || value > today || (busy && !force)) return;
    if (privacyHidden() && selectedDate && !force) {
      // Browsing privately never mutates the editable date or an existing draft.
      privacyBrowseDate = value; calendarMonth = value.slice(0, 7); privateDateInput.value = value;
      $("manual-selected-label").textContent = value.replaceAll("-", "/") + (value === today ? loc(" · 今天") : "");
      renderCalendar();
      return;
    }
    if (!force && value !== selectedDate && !discardDraft()) return;
    statusMessage(""); rebasePending = false; presentTrackingConflict = false; conflictSnapshot = null; undo.reset();
    const entry = entries.find(function (item) { return item.date === value; });
    presentClosed = Boolean(value === today && entry && entry.present_closed);
    selectedDate = value; if (privacyHidden()) privacyBrowseDate = value;
    dayData = null; activeTracking = null; trackingStatusUnavailable = false;
    calendarMonth = value.slice(0, 7); form.elements.date.value = value;
    form.elements.kind.value = initialEditorKind(entry, value, today);
    form.elements.hours.value = entry && entry.kind === "daily_total" ? entry.hours : 11;
    form.elements.note.value = entry && entry.note || "";
    renderIntervals(entry && entry.kind === "intervals_override" && !shouldPrefillIntervals(entry, value, today) ? entry.intervals : []);
    $("manual-selected-label").textContent = value.replaceAll("-", "/") + (value === today ? loc(" · 今天") : "");
    showError(""); baseline = fingerprint(); dayLoading = true; updateFields(); renderCalendar(); return loadDayDetails(value);
  }
  function renderCalendar() {
    const grid = $("manual-calendar-days"); grid.replaceChildren();
    if (!calendarMonth) return;
    if (privacyHidden()) { privateDateInput.max = today; privateDateInput.value = privacyBrowseDate || selectedDate; }
    $("manual-month-label").textContent = window.hourlyI18n && window.hourlyI18n.language() === "en" ?
      new Intl.DateTimeFormat("en", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(calendarMonth + "-01T12:00:00Z")) :
      calendarMonth.slice(0, 4) + loc(" 年 ") + Number(calendarMonth.slice(5)) + loc(" 月");
    monthDays(calendarMonth).forEach(function (day) {
      if (!day) { grid.append(element("span", "manual-calendar-placeholder")); return; }
      const entry = entries.find(function (item) { return item.date === day; });
      const button = element("button", "manual-calendar-day", String(Number(day.slice(8)))); button.type = "button"; button.dataset.date = day;
      const current = privacyHidden() ? (privacyBrowseDate || selectedDate) : selectedDate;
      button.classList.toggle("selected", day === current); button.classList.toggle("today", day === today); button.classList.toggle("has-entry", Boolean(entry));
      button.setAttribute("aria-pressed", String(day === current));
      let description = day.replaceAll("-", "/") + (day === today ? loc(" 今天") : "");
      if (entry) {
        const hours = entry.kind === "daily_total" ? entry.hours : normalizeIntervals(entry.intervals, entry.kind === "intervals_override").minutes / 60;
        if (!privacyHidden()) button.append(element("small", "", Number(hours.toFixed(2)) + "h"));
        description += privacyHidden() ? loc("，已有手动记录，具体数字已隐藏") : loc("，已有补录 ") + formattedHours(Number(hours.toFixed(2)));
      } else description += day > today ? loc("，尚未发生") : loc("，未补录");
      button.setAttribute("aria-label", description); button.disabled = busy || day > today;
      button.addEventListener("click", function () { if (day !== (privacyHidden() ? (privacyBrowseDate || selectedDate) : selectedDate)) loadDate(day); });
      grid.append(button);
    });
    $("manual-prev-month").disabled = busy || calendarMonth <= "0001-01";
    $("manual-next-month").disabled = busy || calendarMonth >= today.slice(0, 7);
  }
  function moveMonth(amount) {
    if (busy || !calendarMonth) return;
    const date = new Date(calendarMonth + "-01T12:00:00Z"); date.setUTCMonth(date.getUTCMonth() + amount);
    calendarMonth = date.toISOString().slice(0, 7); renderCalendar();
  }
  function updatePreview() {
    const todayOverride = selectedDate === today && form.elements.kind.value === "intervals_override";
    const expiredToday = Boolean(selectedDate === today && today && !currentTimeChoice(selectedDate, today, timezone, 0, 1, false));
    const trackingBlocked = trackingSaveBlocked();
    const existing = entries.find(function (entry) { return entry.date === selectedDate; });
    const supplementBlocked = selectedDate === today && activeTracking && existing && existing.kind === "intervals_override" && form.elements.kind.value === "intervals";
    const invalidOrder = form.elements.kind.value !== "daily_total" && rows().length > 0 && !intervalsInOrder(rows(), true);
    $("save-manual").disabled = invalidOrder || busy || expiredToday || trackingBlocked || supplementBlocked || !today || (!dirty() && !presentRow) || (dayLoading && form.elements.kind.value === "intervals_override") || (todayOverride && !(dayData && dayData.today_override_available !== false && Number.isFinite(dayData.edit_cutoff) && typeof dayData.edit_revision === "string")) || (form.elements.kind.value !== "daily_total" && rows().length === 0 && !todayOverride);
    const track = $("manual-time-track"); track.replaceChildren();
    const daily = form.elements.kind.value === "daily_total"; $("manual-time-preview").hidden = daily;
    const changed = dirty();
    $("manual-draft-state").textContent = changed ? loc("有未保存修改") : entries.some(function (entry) { return entry.date === selectedDate; }) ? loc("已加载手动记录") : loc("未保存预览");
    $("manual-draft-state").classList.toggle("unsaved", changed);
    try {
      let minutes, normalized;
      if (daily) minutes = buildEntry(draft(), today).hours * 60;
      else {
        normalized = normalizeIntervals(rows(), todayOverride); minutes = normalized.minutes;
        normalized.ranges.forEach(function (range) {
          const block = element("span", "manual-time-block"); block.style.left = range[0] / 1440 * 100 + "%";
          block.style.width = (range[1] - range[0]) / 1440 * 100 + "%"; block.title = clock(range[0]) + "–" + clock(range[1]); track.append(block);
        });
        const lastIsPresent = Boolean(presentRow && !(presentTrackingConflict && activeTracking && !trackingStatusUnavailable) || presentTrackingConflict && (!activeTracking || trackingStatusUnavailable));
        track.setAttribute("aria-label", loc("24 小时预览：") + normalized.intervals.map(function (item, index) { return item.start + "–" + (lastIsPresent && index === normalized.intervals.length - 1 ? loc("至今") : item.end); }).join(loc("、")));
      }
      $("manual-preview-total").textContent = formattedHours(Number((minutes / 60).toFixed(2)));
      const cutoff = cutoffTime(dayData && dayData.edit_cutoff);
      const manualTail = todayOverride && (presentRow || presentClosed) && cutoff && normalized.intervals.length && normalized.intervals[normalized.intervals.length - 1].end > cutoff;
      $("manual-preview-note").textContent = invalidOrder ? loc("时段有重叠或顺序不对，请调整或移除后再保存；原草稿不会自动改变。") : daily ? loc("按整天总量估算，不虚构具体时段。保存后替代当天合计工时。") : form.elements.kind.value === "intervals_override" ? (todayOverride ? loc("修正截至 ") + (cutoff || loc("加载中")) + loc("。") + (manualTail ? loc("所填末段超出截止的部分将另作手动工作，保存时请确认。") : loc("截止后继续自动记录。")) : loc("保存后以这些时段作为当天工时。")) + loc("原始 VPN 记录保留，可撤销修正。仅预览，保存后生效。") : loc("保存后与 VPN 工时去重。") + (selectedDate === today ? loc("今天只累计已过去的部分。") : "") + loc("仅预览，保存后生效。");
      if (todayOverride && dayData && Array.isArray(dayData.protected_tail_intervals) && dayData.protected_tail_intervals.length) $("manual-preview-note").textContent += loc("上方预览不含已保存的受保护时段；这些时段会继续保留。");
      $("manual-preview-note").classList.toggle("manual-overlap-warning", invalidOrder);
    } catch (error) {
      $("manual-preview-total").textContent = "—"; $("manual-preview-note").textContent = error.message;
      $("manual-preview-note").classList.remove("manual-overlap-warning");
      track.setAttribute("aria-label", loc("请补全有效的工作时段"));
    }
  }
  async function afterManualChange(result, message) {
    // A successful POST is authoritative; a later read failure must never be
    // reported as a failed write or invite the user to submit it again.
    baseline = fingerprint(); rebasePending = false; presentRow = null;
    try {
      if (!result || !Array.isArray(result.entries) || !validDate(result.today)) throw new Error("invalid response");
      entries = result.entries; today = result.today; timezone = result.timezone;
      renderEntries();
      const refresh = loadDate(selectedDate <= today ? selectedDate : today, true);
      window.dispatchEvent(new CustomEvent("hourly:manual-change"));
      const loaded = await refresh;
      statusMessage(loaded ? message : message + loc("，但当天分段刷新失败；请重新打开工作历史查看。"));
    } catch (_) {
      statusMessage(message + loc("，但无法刷新记录；请关闭并重新打开工作历史。"));
      dayData = null; dayLoading = true; updateFields();
      window.dispatchEvent(new CustomEvent("hourly:manual-change"));
    }
  }
  function renderEntries() {
    const list = $("manual-list"); list.replaceChildren(); $("manual-empty").hidden = entries.length > 0;
    $("manual-history-title").textContent = english() ? "View manual records (" + entries.length + (entries.length === 1 ? " day)" : " days)") : "查看已有手动记录（" + entries.length + " 天）";
    entries.slice().sort(function (a, b) { return b.date.localeCompare(a.date); }).forEach(function (entry) {
      const row = element("div", "manual-entry"), detail = element("div", "manual-entry-copy"), actions = element("div", "manual-entry-actions");
      detail.append(element("strong", "", entry.date));
      detail.append(element("p", "", entry.kind === "daily_total" ? loc("手动估算 · ") + formattedHours(entry.hours) : (entry.kind === "intervals_override" ? loc("整日修正 · ") : loc("补充时段 · ")) + entry.intervals.map(function (item) { return item.start + "–" + item.end; }).join(loc("、"))));
      if (entry.note) detail.append(element("p", "manual-entry-note", entry.note));
      const edit = element("button", "secondary-button", loc("编辑")); edit.type = "button"; edit.setAttribute("aria-label", loc("编辑 ") + entry.date + loc(" 的手动记录"));
      edit.addEventListener("click", function () { if (!busy && (entry.date !== selectedDate || discardDraft())) loadDate(entry.date, entry.date === selectedDate); });
      const remove = element("button", "secondary-button", loc("撤销")); remove.type = "button"; remove.setAttribute("aria-label", loc("撤销 ") + entry.date + loc(" 的手动记录"));
      remove.addEventListener("click", async function () {
        if (busy || !discardDraft() || !window.confirm(entry.kind === "intervals_override" ? loc("撤销 ") + entry.date + loc(" 的修正并恢复修正前的记录？原始 VPN 采样不受影响。") : loc("撤销 ") + entry.date + loc(" 的手动记录？这一天会恢复使用原始 VPN 记录。"))) return;
        showError(""); setBusy(true);
        try { const result = await request("/api/manual-entries/delete", { date: entry.date }); await afterManualChange(result, loc("已撤销手动记录")); }
        catch (error) { showError(error.message); }
        finally { setBusy(false); }
      });
      actions.append(edit, remove); row.append(detail, actions); list.append(row);
    });
  }
  async function openManualHistory(targetDate) {
    if (busy || dialog.open) return;
    csrfToken = ""; today = ""; baseline = ""; selectedDate = ""; privacyBrowseDate = ""; calendarMonth = "";
    $("manual-calendar-days").replaceChildren();
    showError(""); statusMessage(""); setBusy(true); dialog.showModal(); $("manual-loading").hidden = false;
    try {
      const results = await Promise.all([request("/api/session"), request("/api/manual-entries")]);
      csrfToken = results[0].csrf_token; entries = Array.isArray(results[1].entries) ? results[1].entries : [];
      today = results[1].today; timezone = results[1].timezone;
      if (!csrfToken || !validDate(today)) throw new Error(loc("本机工作记录信息不完整，请重新打开页面。"));
      const initial = validDate(targetDate) && targetDate <= today ? targetDate : today;
      loadDate(initial, true); renderEntries();
    } catch (error) { showError(error.message); }
    finally {
      $("manual-loading").hidden = true; setBusy(false);
      $("close-manual").focus({ preventScroll: true });
      dialog.scrollTop = 0;
    }
  }
  $("open-manual").addEventListener("click", function () { openManualHistory(""); });
  window.addEventListener("hourly:open-history", function (event) {
    openManualHistory(event.detail && event.detail.date);
  });
  async function refreshCorrectionRange() {
    if (busy || dayLoading || privacyHidden() || form.elements.kind.value !== "intervals_override" || !dayData ||
        !currentTimeChoice(selectedDate, today, timezone, 0, 1, false)) return;
    const date = selectedDate, zone = timezone, original = dayData, draftBefore = JSON.stringify(draft());
    const oldCutoff = original.edit_cutoff;
    const sequence = ++dayRequest;
    showError(""); statusMessage(""); setBusy(true);
    try {
      const latest = await request("/api/history-day?date=" + encodeURIComponent(date));
      if (!dialog.open || sequence !== dayRequest || date !== selectedDate || zone !== timezone || privacyHidden() ||
          !currentTimeChoice(date, today, zone, 0, 1, false) || draftBefore !== JSON.stringify(draft())) {
        throw new Error(loc("日期或草稿已变化，未更新修正范围；请检查后重试。"));
      }
      const active = validateRefreshSnapshot(original, latest, date, zone);
      if (Boolean(active) !== Boolean(activeTracking) && dirty()) {
        freezeConflictDraft(); presentTrackingConflict = true; activeTracking = active;
        throw new Error(loc("自动记录状态已变化；草稿仍在，请先记下修改并重新打开工作历史。"));
      }
      const oldTime = cutoffTime(oldCutoff), newTime = cutoffTime(latest.edit_cutoff);
      if (presentRow && currentTimeChoice(date, today, zone, 0, 1, false) > newTime) {
        throw new Error(active ? loc("至今包含正在自动记录的时段，请等待记录结束后再修正；草稿仍在。") : loc("最新同步尚未覆盖至今，请稍候同步后重试；草稿仍在。"));
      }
      const plan = rebaseIntervals(rows(), latest.editable_intervals, oldTime, newTime);
      if (!window.confirm(loc("将修正截止从 ") + oldTime + loc(" 更新到 ") + newTime + loc("？\n\n") +
          loc("会保留当前草稿，并加入新增范围内已记录的工作时段（比当前填写合计增加 ") + plan.added + loc(" 分钟）。") +
          loc("新增范围内未列出的时间，包括未知时间，将不计入工时。秒级采样按分钟取整，极短片段可能无法表示，请核对。") +
          loc("原始采样保留，修正可以撤销。更新后不会自动保存，截止之后的自动记录仍保留。"))) return;
      if (!dialog.open || sequence !== dayRequest || date !== selectedDate || zone !== timezone || privacyHidden() ||
          !currentTimeChoice(date, today, zone, 0, 1, false) || draftBefore !== JSON.stringify(draft())) {
        throw new Error(loc("日期或草稿已变化，未更新修正范围；请检查后重试。"));
      }
      dayData = latest; activeTracking = active || null; trackingStatusUnavailable = false; undo.reset();
      renderIntervals(plan.intervals, true); rebasePending = true;
      let snapshotHint = $("history-segments").querySelector(".history-edit-snapshot-hint");
      if (!snapshotHint) { snapshotHint = element("p", "field-hint history-edit-snapshot-hint"); $("history-segments").append(snapshotHint); }
      snapshotHint.textContent = loc("修正范围已更新至 ") + newTime + loc("。上方分段仍为上次加载的快照；保存后会刷新。原始 VPN 记录保留，可撤销修正。");
      const beyond = plan.intervals.some(function (span) { return span.end > newTime; });
      statusMessage(loc("修正范围已更新，请核对后保存。") + (beyond ? loc("有时段晚于新截止 ") + newTime + loc("，请调整后再保存。") : ""));
    } catch (error) { showError(error.message || loc("无法更新修正范围；草稿仍在。")); }
    finally { setBusy(false); }
  }
  refreshRange.addEventListener("click", refreshCorrectionRange);
  form.addEventListener("submit", async function (event) {
    event.preventDefault(); if (busy || $("save-manual").disabled) return; showError(""); statusMessage("");
    try {
      if (!csrfToken || !today) throw new Error(loc("工作记录尚未加载，请关闭后重试。"));
      if (selectedDate === today && !currentTimeChoice(selectedDate, today, timezone, 0, 1, false)) throw new Error(loc("日期已变化，不能保存之前的今日修正；草稿仍在，请先记录内容再重新打开工作历史。"));
      updatePresent(true);
      if (form.elements.kind.value !== "daily_total" && !intervalsInOrder(rows(), selectedDate === today && form.elements.kind.value === "intervals_override")) throw new Error(loc("工作时段不能重叠，且须按时间先后排列；请先调整或移除冲突时段。草稿仍在。"));
      const entry = buildEntry(draft(), today, dayData && dayData.edit_cutoff, dayData && dayData.edit_revision);
      if (entry.kind === "intervals_override" && entry.date === today && (presentClosed || presentRow)) {
        if (!dayData || dayData.present_manual_tail_supported !== true) throw new Error(loc("本机服务需要重启后才能保存本次修改；草稿仍在，请先记下修改。"));
        entry.present_closed = true;
      }
      if (entry.kind === "intervals_override" && entry.date === today) {
        const limit = cutoffTime(entry.edit_cutoff);
        if (!limit || entry.intervals.some(function (span) { return span.end > limit; })) {
          if ((presentRow || presentClosed) && limit) {
            const last = entry.intervals[entry.intervals.length - 1];
            if (activeTracking || trackingStatusUnavailable || presentTrackingConflict ||
                entry.intervals.slice(0, -1).some(function (span) { return span.end > limit; })) {
              throw new Error(loc("该时段可能与自动记录重叠，请先核对；草稿仍在。"));
            }
            if (dayData.present_manual_tail_supported !== true) throw new Error(loc("本机服务需要重启后才能保存至今；草稿仍在，请先记下修改。"));
            const after = last.start > limit ? last.start : limit;
            const beforeConfirm = JSON.stringify(draft());
            if (!await confirmManualTail(after, last.end, limit)) return;
            if (beforeConfirm !== JSON.stringify(draft()) || activeTracking || trackingStatusUnavailable || presentTrackingConflict ||
                !currentTimeChoice(selectedDate, today, timezone, 0, 1, false)) throw new Error(loc("状态或草稿已变化，请核对后重试；草稿仍在。"));
            entry.present_end = last.end;
          } else {
          throw new Error(loc("今天修正的时段不能晚于截止时间 ") + (limit || loc("（未知）")) + loc("；之后的时段继续自动记录。"));
          }
        }
      }
      setBusy(true);
      const result = await request("/api/manual-entries", { entries: [entry] });
      await afterManualChange(result, loc("已保存修改"));
    } catch (error) { showError(error.message); }
    finally { setBusy(false); }
  });
  form.elements.kind.addEventListener("change", function () { undo.reset(); showError(""); updateFields(); });
  form.elements.hours.addEventListener("input", updatePreview); form.elements.note.addEventListener("input", updatePreview);
  form.elements.date.addEventListener("change", function () {
    const value = form.elements.date.value; form.elements.date.value = selectedDate;
    if (!validDate(value) || value > today) { showError(loc("请选择今天或过去的日期。")); return; }
    if (value !== selectedDate) loadDate(value);
  });
  $("manual-add-interval").addEventListener("click", function () {
    if (busy || rows().length >= 12) return;
    try {
      if (presentRow) updatePresent(false);
      const values = rows(), next = insertionForGap(values, editLimit()), before = undoState();
      values.splice(next.index, 0, next.interval);
      if (next.index === values.length - 1 && !(dayData && Array.isArray(dayData.protected_tail_intervals) && dayData.protected_tail_intervals.length)) presentClosed = false;
      renderIntervals(values, true); recordUndo(before); showError(""); updateFields();
    } catch (error) { showError(error.message); }
  });
  $("manual-copy-previous").addEventListener("click", function () {
    const entry = previousEntry(); if (busy || !entry || !discardDraft()) return;
    undo.reset();
    form.elements.kind.value = entry.kind;
    if (!numbersHidden()) form.elements.note.value = loc("参考 ") + entry.date + loc(" 的手动记录");
    if (entry.kind === "daily_total") form.elements.hours.value = entry.hours;
    else renderIntervals(entry.intervals);
    showError(""); updateFields();
  });
  form.querySelectorAll("[data-manual-hours]").forEach(function (button) {
    button.addEventListener("click", function () { if (!busy) { form.elements.hours.value = button.dataset.manualHours; updatePreview(); } });
  });
  $("manual-prev-month").addEventListener("click", function () { moveMonth(-1); });
  $("manual-next-month").addEventListener("click", function () { moveMonth(1); });
  function goToday() { if (!busy && today) { if (privacyHidden()) loadDate(today); else if (today === selectedDate) { calendarMonth = today.slice(0, 7); renderCalendar(); } else loadDate(today); } }
  $("manual-today").addEventListener("click", goToday); $("new-manual").addEventListener("click", goToday);
  function close() {
    if (!busy && discardDraft()) { baseline = ""; presentRow = null; dialog.close(); }
  }
  $("close-manual").addEventListener("click", close); $("cancel-manual").addEventListener("click", close);
  dialog.addEventListener("cancel", function (event) { event.preventDefault(); close(); });
  window.addEventListener("hourly:language-change", function () {
    privacyNotice.querySelector("p").textContent = loc("可浏览日历和色块；工时及具体时段已隐藏。显示时间后可编辑；未保存的修改会保留。");
    privacyReveal.textContent = loc("显示时间");
    noteNotice.textContent = loc("备注已隐藏；保存时会保留备注，显示数字后可编辑。");
    privateDateJump.firstChild.nodeValue = loc("跳转到日期");
    refreshRange.textContent = loc("更新可修正范围");
    refreshRange.title = loc("保留草稿，检查最新记录并在确认后更新截止时间");
    editorModes.setAttribute("aria-label", loc("工作时段编辑方式"));
    timelineMode.textContent = loc("滑动时间轴"); preciseMode.textContent = loc("精确选择时间");
    undoButton.textContent = loc("撤销上一步");
    undoButton.title = undoAvailable ? loc("撤销本次编辑中的上一个时段操作") : loc("请重启本机服务后使用撤销");
    closedPresent.textContent = loc("至今 · 之后无新增手动工作，自动计时仍按当前状态运行");
    if (!dialog.open) return;
    const shownDate = privacyHidden() ? (privacyBrowseDate || selectedDate) : selectedDate;
    if (shownDate) $("manual-selected-label").textContent = shownDate.replaceAll("-", "/") + (shownDate === today ? loc(" · 今天") : "");
    if (dayData && !dayLoading) renderDayPanel(selectedDate, dayData, dayWasPrefilled);
    renderEntries(); renderCalendar(); updateFields();
  });
  window.addEventListener("beforeunload", function (event) { if (dialog.open && dirty()) { event.preventDefault(); event.returnValue = ""; } });
})();
