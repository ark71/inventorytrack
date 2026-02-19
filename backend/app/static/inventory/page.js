// static/inventory/page.js
(function () {
  "use strict";

  const S = window.InventoryState;
  const API = window.InventoryAPI;

  async function refreshCounts() {
    const { res, data } = await API.inventoryStatus();
    if (!res.ok || !data) return;
    const u = document.getElementById("unconverted");
    const c = document.getElementById("invcount");
    if (u) u.textContent = data.unconverted_purchase_lines;
    if (c) c.textContent = data.inventory_items;
  }

  function setActiveTab(tab) {
    const needsBtn = document.getElementById("tabNeedsSplit");
    const unlistBtn = document.getElementById("tabUnlisted");

    const needsPanel = document.getElementById("panelNeedsSplit");
    const unlistPanel = document.getElementById("panelUnlisted");

    const isNeeds = tab === "needs_split";
    S.activeTab = isNeeds ? "needs_split" : "unlisted";

    needsPanel.style.display = isNeeds ? "" : "none";
    unlistPanel.style.display = isNeeds ? "none" : "";

    needsBtn.classList.toggle("active", isNeeds);
    unlistBtn.classList.toggle("active", !isNeeds);

    if (isNeeds) window.InventoryLists.loadNeedsSplit();
    else window.InventoryLists.loadUnlisted();
  }

  async function refreshAll() {
    await refreshCounts();
    await window.InventorySalesMatch.loadUnmatchedSales();
    if (S.activeTab === "needs_split") await window.InventoryLists.loadNeedsSplit();
    else await window.InventoryLists.loadUnlisted();
  }

  function init(opts) {
    // bind once
    window.InventorySalesMatch.bindSalesUI();
    window.InventoryLists.bindInventoryUI();
    window.InventorySplitDialog.bindSplitUI();
    window.InventoryManualEntry.bindManualEntryUI();

    document.getElementById("tabNeedsSplit")?.addEventListener("click", () => setActiveTab("needs_split"));
    document.getElementById("tabUnlisted")?.addEventListener("click", () => setActiveTab("unlisted"));
    document.getElementById("refreshBtn")?.addEventListener("click", refreshAll);

    // initial
    const initial = (opts && opts.initialView) ? String(opts.initialView) : "";
    setActiveTab(initial === "unlisted" ? "unlisted" : "needs_split");

    // load counts + sales
    refreshCounts();
    window.InventorySalesMatch.loadUnmatchedSales();
  }

  window.InventoryPage = {
    init,
    refreshCounts,
    refreshAll,
    setActiveTab,
  };
})();

