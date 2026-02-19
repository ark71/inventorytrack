// static/inventory/split_dialog.js
(function () {
  "use strict";

  const API = window.InventoryAPI;
  const R = window.InventoryRender;

  let currentSplitId = null;

  function goodwillItemUrl(itemId) {
    return itemId ? `https://shopgoodwill.com/item/${itemId}` : "";
  }
  function goodwillOrderUrl(orderNum) {
    return orderNum ? `https://shopgoodwill.com/shopgoodwill/order/${orderNum}` : "";
  }

  function openSplitDialog(containerId, containerTitle, goodwillItemId, orderNum) {
    currentSplitId = containerId;

    const itemUrl = goodwillItemUrl(goodwillItemId);
    const orderUrl = goodwillOrderUrl(orderNum);

    const metaLines = [];
    metaLines.push(`<b>Container:</b> ${R.esc(containerTitle)}`);
    if (goodwillItemId) metaLines.push(`<b>Item ID:</b> <a href="${itemUrl}" target="_blank" rel="noopener noreferrer">${R.esc(goodwillItemId)}</a>`);
    if (orderNum) metaLines.push(`<b>Order #:</b> <a href="${orderUrl}" target="_blank" rel="noopener noreferrer">${R.esc(orderNum)}</a>`);

    document.getElementById("splitMeta").innerHTML = metaLines.join("<br>");
    document.getElementById("splitTitles").value = "";
    document.getElementById("splitResult").textContent = "{}";

    document.getElementById("splitDialog").showModal();
    setTimeout(() => document.getElementById("splitTitles")?.focus(), 0);
  }

  async function submitSplit() {
    const out = document.getElementById("splitResult");
    const titlesText = document.getElementById("splitTitles")?.value || "";

    if (!currentSplitId) return;

    out.textContent = "Working...";

    const { res, txt } = await API.inventorySplitWithTitles(currentSplitId, titlesText);

    let parsed = null;
    try { parsed = JSON.parse(txt); } catch {}

    out.textContent = parsed ? JSON.stringify(parsed, null, 2) : txt;

    if (parsed && parsed.ok) {
      R.setStatus(`✅ Split complete: created ${parsed.inserted_children} items.`);
      await window.InventoryPage.refreshCounts();
      await window.InventorySalesMatch.loadUnmatchedSales();
      await window.InventoryLists.loadNeedsSplit();
      await window.InventoryLists.loadUnlisted();
      document.getElementById("splitDialog").close();
    } else if (parsed && parsed.error) {
      R.setStatus(`⚠️ Split failed: ${parsed.error}`);
    }
  }

  function bindSplitUI() {
    document.getElementById("splitCloseBtn")?.addEventListener("click", () => {
      document.getElementById("splitDialog")?.close();
    });

    document.getElementById("genLinesBtn")?.addEventListener("click", () => {
      const n = parseInt(document.getElementById("splitCount")?.value || "1", 10);
      const lines = [];
      for (let i = 1; i <= Math.min(Math.max(n, 1), 500); i++) lines.push(`Item ${i}`);
      document.getElementById("splitTitles").value = lines.join("\n");
    });

    document.getElementById("splitSubmitBtn")?.addEventListener("click", submitSplit);
  }

  window.InventorySplitDialog = {
    bindSplitUI,
    openSplitDialog,
  };
})();

