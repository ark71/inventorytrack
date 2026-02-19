// static/inventory/manual_entry.js
(function () {
  "use strict";

  const API = window.InventoryAPI;

  function bindManualEntryUI() {
    const btn = document.getElementById("manualCreateBtn");
    const msg = document.getElementById("manualCreateMsg");

    if (!btn || !msg) return;

    btn.addEventListener("click", async () => {
      msg.textContent = "";

      const payload = {
        title: document.getElementById("manualTitle")?.value.trim(),
        cost_total: document.getElementById("manualCost")?.value.trim() || 0,
        system_code: document.getElementById("manualSystem")?.value,
        item_id: document.getElementById("manualItemId")?.value.trim() || null,
        mode: document.getElementById("manualMode")?.value,
      };

      if (!payload.title) {
        msg.textContent = "❌ Title is required.";
        return;
      }

      const { res, data, txt } = await API.inventoryManualCreate(payload);

      if (!res.ok || !data || !data.ok) {
        msg.textContent = "❌ " + ((data && (data.detail || data.error)) ? (data.detail || data.error) : txt || "Failed");
        return;
      }

      msg.textContent = `✅ Created #${data.id} (${data.sku})`;

      // reload is simplest + consistent (manual entry changes multiple panels)
      window.location.reload();
    });
  }

  window.InventoryManualEntry = { bindManualEntryUI };
})();

