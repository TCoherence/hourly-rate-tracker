(() => {
  "use strict";

  const storageKey = "hourly-rate-theme";
  const privacyKey = "hourly-privacy-hidden";
  const privacyV2Key = "hourly-privacy-v2";
  let numbersHidden = false;
  let timeHidden = false;
  let privacyStorageAvailable = true;
  function parsePrivacy(value) {
    if (typeof value !== "string") return null;
    try {
      const parsed = JSON.parse(value);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)
          && typeof parsed.numbers === "boolean" && typeof parsed.time === "boolean") {
        return { numbers: parsed.numbers, time: parsed.time };
      }
    } catch (_) { /* Invalid stored preferences are handled conservatively. */ }
    return null;
  }
  try {
    const raw = window.localStorage.getItem(privacyV2Key);
    const saved = parsePrivacy(raw);
    const legacy = window.localStorage.getItem(privacyKey);
    // A corrupted v2 record must not reveal numbers accidentally.
    numbersHidden = saved ? saved.numbers : raw !== null || legacy === "1";
    timeHidden = saved ? saved.time : raw !== null || legacy === "1";
    if (raw === null && legacy === "1") {
      window.localStorage.setItem(privacyV2Key, JSON.stringify({ numbers: true, time: true }));
    }
  } catch (_) { privacyStorageAvailable = false; }
  const fallback = new URLSearchParams(window.location.search).get("privacy");
  if (fallback === "1" || fallback === "numbers" || fallback === "time") {
    // A navigation fallback may only add protections. It must never reveal a
    // different dimension already hidden in the saved browser preference.
    numbersHidden = numbersHidden || fallback !== "time";
    timeHidden = timeHidden || fallback !== "numbers";
    // A prior navigation may have carried the preference while storage was
    // unavailable; retain it once storage is usable again.
    try {
      window.localStorage.setItem(privacyV2Key, JSON.stringify({ numbers: numbersHidden, time: timeHidden }));
      window.localStorage.setItem(privacyKey, "1");
      privacyStorageAvailable = true;
    } catch (_) { privacyStorageAvailable = false; }
  }
  function fallbackValue() {
    return numbersHidden && timeHidden ? "1" : numbersHidden ? "numbers" : timeHidden ? "time" : "";
  }
  function applyPrivacy(numbers, time, persist) {
    numbersHidden = Boolean(numbers);
    timeHidden = Boolean(time);
    const anyHidden = numbersHidden || timeHidden;
    document.documentElement.dataset.privacyReady = anyHidden ? "false" : "true";
    document.documentElement.dataset.privacy = anyHidden ? "hidden" : "shown";
    document.documentElement.dataset.privacyNumbers = numbersHidden ? "hidden" : "shown";
    document.documentElement.dataset.privacyTime = timeHidden ? "hidden" : "shown";
    if (persist) {
      try {
        window.localStorage.setItem(privacyV2Key, JSON.stringify({ numbers: numbersHidden, time: timeHidden }));
        // Old open tabs only understand one switch. Keep them conservative.
        window.localStorage.setItem(privacyKey, anyHidden ? "1" : "0");
        privacyStorageAvailable = true;
      } catch (_) { privacyStorageAvailable = false; }
      if (!anyHidden && new URLSearchParams(window.location.search).has("privacy")) {
        const url = new URL(window.location.href); url.searchParams.delete("privacy");
        window.history.replaceState(null, "", url.pathname + url.search + url.hash);
      }
    }
    window.dispatchEvent(new CustomEvent("hourly:privacy-change", { detail: { hidden: anyHidden, numbersHidden: numbersHidden, timeHidden: timeHidden } }));
  }
  window.hourlyPrivacy = {
    isHidden: () => numbersHidden || timeHidden,
    setHidden: hidden => applyPrivacy(hidden, hidden, true),
    isNumbersHidden: () => numbersHidden,
    isTimeHidden: () => timeHidden,
    setNumbersHidden: hidden => applyPrivacy(hidden, timeHidden, true),
    setTimeHidden: hidden => applyPrivacy(numbersHidden, hidden, true),
    canPersist: () => privacyStorageAvailable,
    fallbackValue: fallbackValue,
  };
  // Before the first paint, hide sensitive elements if the user previously chose privacy mode.
  document.documentElement.dataset.privacyReady = numbersHidden || timeHidden ? "false" : "true";
  document.documentElement.dataset.privacy = numbersHidden || timeHidden ? "hidden" : "shown";
  document.documentElement.dataset.privacyNumbers = numbersHidden ? "hidden" : "shown";
  document.documentElement.dataset.privacyTime = timeHidden ? "hidden" : "shown";
  window.addEventListener("storage", event => {
    // Clearing storage is not an explicit request to reveal private values.
    if (event.key === privacyV2Key) {
      const value = parsePrivacy(event.newValue);
      if (value) applyPrivacy(value.numbers, value.time, false);
    } else if (event.key === privacyKey && (event.newValue === "0" || event.newValue === "1")) {
      // Only listen to the legacy key before a valid v2 preference exists.
      try {
        if (!parsePrivacy(window.localStorage.getItem(privacyV2Key))) {
          applyPrivacy(event.newValue === "1", event.newValue === "1", false);
        }
      } catch (_) { /* Keep the last known state if storage is unavailable. */ }
    }
  });
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const validPreference = value => ["system", "light", "dark"].includes(value);
  let preference = "system";
  let control;

  try {
    const saved = window.localStorage.getItem(storageKey);
    if (validPreference(saved)) preference = saved;
  } catch (_) {
    // Theme switching also works when browser storage is unavailable.
  }

  function applyTheme() {
    document.documentElement.dataset.theme = preference === "system"
      ? (media.matches ? "dark" : "light") : preference;
    document.documentElement.dataset.themePreference = preference;
    if (control) control.value = preference;
  }

  // This script runs before the stylesheet to avoid a light first frame.
  applyTheme();

  function onSystemChange() {
    if (preference === "system") applyTheme();
  }
  if (media.addEventListener) media.addEventListener("change", onSystemChange);
  else media.addListener(onSystemChange);

  window.addEventListener("storage", event => {
    if (event.key !== storageKey && event.key !== null) return;
    preference = validPreference(event.newValue) ? event.newValue : "system";
    applyTheme();
  });

  document.addEventListener("DOMContentLoaded", () => {
    control = document.getElementById("theme-mode");
    if (!control) return;
    control.value = preference;
    control.addEventListener("change", () => {
      if (!validPreference(control.value)) return;
      preference = control.value;
      applyTheme();
      try {
        window.localStorage.setItem(storageKey, preference);
      } catch (_) {
        // Keep the selected appearance for this page even without storage.
      }
    });
  });
})();
