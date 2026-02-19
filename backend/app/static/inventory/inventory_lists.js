// static/inventory/inventory_lists.js
(function () {
  "use strict";

  const S = window.InventoryState;
  const API = window.InventoryAPI;
  const R = window.InventoryRender;

  async function loadNeedsSplit() {
    const body = document.getElementById("needsSplitBody");
    if (body) body.innerHTML = `<tr><td colspan="4">Loading...</td></tr>`;

    const { res, data } = await API.inventoryNeedsSplit();
    const rows = (data && data.items) ? data.items : [];

    S.needsSplitById = {};
    for (const r of rows) S.needsSplitById[r.id] = r;

    R.renderNeedsSplitTable(rows);
    return rows;
  }

  async function loadUnlisted() {
    const body = document.getElementById("unlistedBody");
    if (body) body.innerHTML = `<tr><td colspan="5">Loading...</td></tr>`;

    const { res, data } = await API.inventoryUnlisted();
    const rows = (data && data.items) ? data.items : [];

    if (!res.ok) {
      if (body) body.innerHTML = `<tr><td colspan="5">Failed to load.</td></tr>`;
      return [];
    }

    R.renderUnlistedTable(rows);
    return rows;
  }

  async function saveItem(itemId) {
    const sku = document.getElementById(`sku_${itemId}`)?.value || "";
    const location = document.getElementById(`loc_${itemId}`)?.value || "";

    R.setResult("Saving...");

    const { res, txt } = await API.inventoryUpdate(itemId, sku, location);
    try { R.setResult(JSON.parse(txt)); } catch { R.setResult(txt); }

    if (!res.ok) {
      R.setStatus("⚠️ Save failed");
      return false;
    }
    return true;
  }

  function bindInventoryUI() {
    // Save + split open via event delegation
    document.addEventListener("click", async (e) => {
      const saveBtn = e.target.closest(".js-inv-save");
      if (saveBtn) {
        const id = parseInt(saveBtn.dataset.itemId || "0", 10);
        if (id) await saveItem(id);
        return;
      }

      const splitBtn = e.target.closest(".js-split-open");
      if (splitBtn) {
        const id = parseInt(splitBtn.dataset.containerId || "0", 10);
        if (!id) return;
        const r = S.needsSplitById[id];
        if (!r) return;
        window.InventorySplitDialog.openSplitDialog(
          r.id,
          (r.title || "").toString(),
          (r.goodwill_item_id || "").toString(),
          (r.order_number || "").toString()
        );
      }
    });
  }

  window.InventoryLists = {
    bindInventoryUI,
    loadNeedsSplit,
    loadUnlisted,
    saveItem,
  };
})();

