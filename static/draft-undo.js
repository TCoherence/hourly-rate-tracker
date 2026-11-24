/* In-memory undo for one work-history draft. No draft is persisted here. */
(function (root) {
  "use strict";

  function copy(value) { return JSON.parse(JSON.stringify(value)); }
  function fingerprint(value) {
    const state = copy(value);
    // A running “present” endpoint advances without being a user edit.
    if (state.present && Array.isArray(state.intervals) && state.intervals.length) {
      state.intervals[state.intervals.length - 1].end = "__present__";
    }
    return JSON.stringify(state);
  }
  function createDraftUndo(limit) {
    const max = Number.isInteger(limit) && limit > 0 ? limit : 50;
    let entries = [], currentGroup = null;
    return {
      // `before` and `after` include date, intervals and any editor metadata.
      // Consecutive changes sharing one group (a drag) become one step.
      record: function (before, after, group) {
        if (!before || !after || before.date !== after.date || fingerprint(before) === fingerprint(after)) return false;
        const grouped = group !== undefined && group !== null;
        if (!grouped || currentGroup !== group) {
          entries.push(copy(before));
          if (entries.length > max) entries.shift();
        }
        currentGroup = grouped ? group : null;
        return true;
      },
      endGroup: function () { currentGroup = null; },
      // Peek before restoring so a changed live-recording boundary can block
      // a now-unsafe undo without destroying the user's undo history.
      peek: function (date) {
        const last = entries[entries.length - 1];
        return last && last.date === date ? copy(last) : null;
      },
      discard: function (date) {
        if (!entries.length || entries[entries.length - 1].date !== date) return false;
        entries.pop(); currentGroup = null; return true;
      },
      reset: function () { entries = []; currentGroup = null; },
      size: function () { return entries.length; }
    };
  }
  const api = { createDraftUndo: createDraftUndo, fingerprint: fingerprint };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.hourlyDraftUndo = api;
})(typeof window === "undefined" ? globalThis : window);
