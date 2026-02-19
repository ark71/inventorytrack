// static/inventory/api.js
(function () {
  "use strict";

  async function fetchText(url, opts) {
    const res = await fetch(url, opts || {});
    const txt = await res.text();
    return { res, txt };
  }

  async function fetchJSON(url, opts) {
    const res = await fetch(url, opts || {});
    const txt = await res.text();
    let data = null;
    try { data = JSON.parse(txt); } catch { /* ignore */ }
    return { res, data, txt };
  }

  const API = {
    // inventory
    inventoryStatus: () => fetchJSON("/inventory/status", { cache: "no-store" }),
    inventoryNeedsSplit: () => fetchJSON("/api/inventory/needs_split", { cache: "no-store" }),
    inventoryUnlisted: () => fetchJSON("/api/inventory/unlisted", { cache: "no-store" }),
    inventoryUpdate: (id, sku, location) => fetchText(
      `/inventory/update/${id}?sku=${encodeURIComponent(sku || "")}&location=${encodeURIComponent(location || "")}`,
      { method: "POST" }
    ),
    inventorySplitWithTitles: (containerId, titlesText) => fetchText(
      `/inventory/split-with-titles/${containerId}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ titles_text: titlesText || "" })
      }
    ),
    inventoryManualCreate: (payload) => fetchJSON(
      "/api/inventory/manual",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {})
      }
    ),

    // sales
    salesUnmatched: (limit) => fetchJSON(`/api/sales/unmatched?limit=${encodeURIComponent(limit || 200)}`, { cache: "no-store" }),
    salesMatch: (saleId, inventoryItemId) => fetchJSON(
      "/api/sales/match",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sale_id: saleId, inventory_item_id: inventoryItemId })
      }
    )
  };

  window.InventoryAPI = API;
})();

