// static/inventory/sales_match.js
(function () {
  "use strict";

  const S = window.InventoryState;
  const API = window.InventoryAPI;
  const R = window.InventoryRender;

  async function loadUnmatchedSales() {
    const body = document.getElementById("unmatchedSalesBody");
    const countEl = document.getElementById("unmatchedSalesCount");
    if (body) body.innerHTML = `<tr><td colspan="5">Loading...</td></tr>`;
    if (countEl) countEl.textContent = "...";

    const { res, data } = await API.salesUnmatched(200);
    if (!res.ok || !data || !data.ok) {
      if (body) body.innerHTML = `<tr><td colspan="5">Failed to load unmatched sales.</td></tr>`;
      if (countEl) countEl.textContent = "—";
      return [];
    }

    const rows = data.items || [];
    S.unmatchedSalesById = {};
    for (const r of rows) S.unmatchedSalesById[r.id] = r;

    R.renderUnmatchedSalesTable(rows);
    return rows;
  }

  async function loadCandidateInventoryIfNeeded() {
    if (S.candidateInventoryCache) return S.candidateInventoryCache;

    // Candidate pool = unlisted for now (lean + already exists)
    const { res, data } = await API.inventoryUnlisted();
    if (!res.ok || !data) {
      S.candidateInventoryCache = [];
      return S.candidateInventoryCache;
    }

    S.candidateInventoryCache = (data.items || []).map(x => ({
      id: x.id,
      title: x.title || "",
      cost_total: x.cost_total ?? 0,
      sku: x.sku || "",
      location: x.location || "",
      status: x.status || "unlisted",
      acquired_date: x.acquired_date || ""
    }));

    return S.candidateInventoryCache;
  }

  function _filterCandidates(q) {
    const needle = (q || "").trim().toLowerCase();
    const all = S.candidateInventoryCache || [];
    const rows = all.filter(it => {
      if (!needle) return true;
      return (
        (it.sku || "").toLowerCase().includes(needle) ||
        (it.title || "").toLowerCase().includes(needle) ||
        (it.location || "").toLowerCase().includes(needle)
      );
    }).slice(0, 200);
    return rows;
  }

  function renderCandidates(q) {
    const rows = _filterCandidates(q);
    R.renderMatchCandidatesTable(rows, S.currentChosenInventoryId);
  }

  async function openMatchDialog(saleId) {
    const sale = S.unmatchedSalesById[saleId];
    if (!sale) return;

    S.currentSaleToMatchId = saleId;
    S.currentChosenInventoryId = null;

    const metaEl = document.getElementById("matchSaleMeta");
    const msgEl = document.getElementById("matchSaleMsg");
    const searchEl = document.getElementById("matchSearch");
    const bodyEl = document.getElementById("matchCandidatesBody");

    if (msgEl) msgEl.textContent = "";
    if (searchEl) searchEl.value = "";
    if (bodyEl) bodyEl.innerHTML = `<tr><td colspan="6">Loading...</td></tr>`;

    const net = (sale.net_payout ?? 0).toFixed(2);
    if (metaEl) {
      metaEl.innerHTML = [
        `<b>Sale #:</b> ${sale.id}`,
        sale.sold_at ? `<b>Sold at:</b> ${R.esc(sale.sold_at)}` : "",
        sale.sku ? `<b>SKU:</b> ${R.esc(sale.sku)}` : "",
        `<b>Net payout:</b> $${net}`,
        `<b>Title:</b> ${R.esc(sale.title || "")}`,
      ].filter(Boolean).join("<br>");
    }

    await loadCandidateInventoryIfNeeded();
    renderCandidates("");

    const dlg = document.getElementById("matchSaleDialog");
    dlg.showModal();
    setTimeout(() => document.getElementById("matchSearch")?.focus(), 0);
  }

  async function confirmMatch() {
    const msgEl = document.getElementById("matchSaleMsg");
    if (!S.currentSaleToMatchId) return;

    if (!S.currentChosenInventoryId) {
      if (msgEl) msgEl.textContent = "❌ Pick an inventory item first.";
      return;
    }

    if (msgEl) msgEl.textContent = "Matching...";

    const { res, data, txt } = await API.salesMatch(S.currentSaleToMatchId, S.currentChosenInventoryId);
    if (!res.ok || !data || data.ok !== true) {
      const err = (data && (data.detail || data.error)) ? (data.detail || data.error) : txt;
      if (msgEl) msgEl.textContent = "❌ " + err;
      return;
    }

    if (msgEl) msgEl.textContent = "✅ Matched.";

    // close + refresh
    document.getElementById("matchSaleDialog").close();
    S.candidateInventoryCache = null;

    // remove locally for snappiness
    delete S.unmatchedSalesById[S.currentSaleToMatchId];

    await loadUnmatchedSales();
    await window.InventoryPage.refreshCounts();
    await window.InventoryLists.loadUnlisted();
  }

  function bindSalesUI() {
    document.getElementById("refreshUnmatchedBtn")?.addEventListener("click", async () => {
      S.candidateInventoryCache = null;
      await loadUnmatchedSales();
    });

    document.getElementById("matchSaleCloseBtn")?.addEventListener("click", () => {
      document.getElementById("matchSaleDialog")?.close();
    });

    document.getElementById("matchConfirmBtn")?.addEventListener("click", confirmMatch);

    document.getElementById("matchSearch")?.addEventListener("input", (e) => {
      renderCandidates(e.target.value || "");
    });

    // Event delegation: match button clicks + radio picks
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".js-sale-match");
      if (btn) {
        const saleId = parseInt(btn.dataset.saleId || "0", 10);
        if (saleId) openMatchDialog(saleId);
        return;
      }

      const mini = e.target.closest(".js-miniwin");
      if (mini) {
        const url = mini.dataset.url || mini.getAttribute("href") || "";
        if (url) {
          e.preventDefault();
          R.openMiniWindow(url);
        }
      }
    });

    document.addEventListener("change", (e) => {
      const pick = e.target.closest(".js-match-pick");
      if (pick) {
        S.currentChosenInventoryId = parseInt(pick.dataset.itemId || "0", 10) || null;
        const msgEl = document.getElementById("matchSaleMsg");
        if (msgEl) msgEl.textContent = "";
      }
    });
  }

  window.InventorySalesMatch = {
    bindSalesUI,
    loadUnmatchedSales,
  };
})();

