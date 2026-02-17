(function () {
  const defaults = {
    theme: "goodwill",          // emerald | amber | violet | mono
    density: "comfy",          // compact | comfy | cozy
    layout: "wide"             // narrow | wide
  };

  function loadPrefs() {
    try {
      return Object.assign({}, defaults, JSON.parse(localStorage.getItem("it_prefs") || "{}"));
    } catch {
      return defaults;
    }
  }

  function applyPrefs(p) {
    document.documentElement.dataset.theme = p.theme;

    document.body.classList.remove("density-compact","density-comfy","density-cozy","layout-narrow","layout-wide");
    document.body.classList.add(`density-${p.density}`, `layout-${p.layout}`);
  }

  // Expose a tiny API for later (theme switcher page)
  window.InventoryTrackTheme = {
    get: loadPrefs,
    set: (patch) => {
      const next = Object.assign(loadPrefs(), patch);
      localStorage.setItem("it_prefs", JSON.stringify(next));
      applyPrefs(next);
      return next;
    }
  };

  // Apply on load
  document.addEventListener("DOMContentLoaded", () => applyPrefs(loadPrefs()));
})();
