// static/inventory/render.js
(function () {
  "use strict";

  function esc(s) {
    return (s ?? "").toString()
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function setStatus(msg) {
    const el = document.getElementById("statusMsg");
    if (!el) return;
    el.textContent = msg || "";
  }

  function setResult(objOrText) {
    const out = document.getElementById("result");
    if (!out) return;
    if (typeof objOrText === "string") {
      out.textContent = objOrText;
      return;
    }
    try { out.textContent = JSON.stringify(objOrText, null, 2); }
    catch { out.textContent = String(objOrText); }
  }

  function openMiniWindow(url) {
    const w = 980;
    const h = 780;
    const left = Math.max(0, Math.round((window.screen.width - w) / 2));
    const top  = Math.max(0, Math.round((window.screen.height - h) / 2));
    const features = [
      `width=${w}`,
      `height=${h}`,
      `left=${left}`,
      `top=${top}`,
      "resizable=yes",
      "scrollbars=yes",
      "toolbar=no",
      "menubar=no",
      "location=yes",
      "status=no"
    ].join(",");
    const win = window.open(url, "_blank", features);
    if (win) win.focus();
    return false;
  }

  function renderUnmatchedSalesTable(rows) {
    const body = document.getElementById("unmatchedSalesBody");
    const countEl = document.getElementById("unmatchedSalesCount");
    if (!body || !countEl) return;

    countEl.textContent = String(rows.length);

    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="5">No unmatched sales 🎉</td></tr>`;
      return;
    }

    body.innerHTML = rows.map(r => {
      const soldAt = esc(r.sold_at || "");
      const title = esc(r.title || "");
      const net = (r.net_payout ?? 0).toFixed(2);
      const sku = esc(r.sku || "");
      return `
        <tr>
          <td>${soldAt || "<span class='small'>—</span>"}</td>
          <td><b>${title}</b></td>
          <td>$${net}</td>
          <td>${sku || "<span class='small'>—</span>"}</td>
          <td><button type="button" class="js-sale-match" data-sale-id="${r.id}">Match</button></td>
        </tr>
      `;
    }).join("");
  }

  function renderNeedsSplitTable(rows) {
    const body = document.getElementById("needsSplitBody");
    if (!body) return;

    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="4">No containers need split 🎉</td></tr>`;
      return;
    }

    body.innerHTML = rows.map(r => {
      const title = esc(r.title);
      const meta = `<div class="small">${esc(r.category || "")}<br>${esc(r.acquired_date || "")}</div>`;

      const itemId = esc(r.goodwill_item_id || "");
      const orderNum = esc(r.order_number || "");

      const itemUrl = itemId ? `https://shopgoodwill.com/item/${itemId}` : "";
      const orderUrl = orderNum ? `https://shopgoodwill.com/shopgoodwill/order/${orderNum}` : "";

      const goodwill = `
        <div>
          <div>
            <b>Item ID:</b>
            ${
              itemId
                ? `<a href="${itemUrl}" class="js-miniwin" data-url="${esc(itemUrl)}" target="_blank" rel="noopener noreferrer">${itemId}</a>`
                : `<span class="small">—</span>`
            }
          </div>
          <div class="small" style="margin-top:6px;">
            <b>Order #:</b>
            ${
              orderNum
                ? `<a href="${orderUrl}" class="js-miniwin" data-url="${esc(orderUrl)}" target="_blank" rel="noopener noreferrer">${orderNum}</a>`
                : `<span>—</span>`
            }
          </div>
        </div>
      `;

      const cost = (r.cost_total ?? 0).toFixed(2);

      return `
        <tr>
          <td><b>${title}</b>${meta}</td>
          <td>${goodwill}</td>
          <td>$${cost}</td>
          <td><button type="button" class="js-split-open" data-container-id="${r.id}">Split (enter titles)</button></td>
        </tr>
      `;
    }).join("");
  }

  function renderUnlistedTable(rows) {
    const body = document.getElementById("unlistedBody");
    if (!body) return;

    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="5">No unlisted items 🎉</td></tr>`;
      return;
    }

    body.innerHTML = rows.map(r => {
      const title = esc(r.title);
      const cost = (r.cost_total ?? 0).toFixed(2);
      return `
        <tr>
          <td><b>${title}</b><div class="small">${esc(r.acquired_date || "")}</div></td>
          <td>$${cost}</td>
          <td><input id="sku_${r.id}" value="${esc(r.sku || "")}" placeholder="SKU" style="width:140px;"></td>
          <td><input id="loc_${r.id}" value="${esc(r.location || "")}" placeholder="Bin/Shelf" style="width:140px;"></td>
          <td><button type="button" class="js-inv-save" data-item-id="${r.id}">Save</button></td>
        </tr>
      `;
    }).join("");
  }

  function renderMatchCandidatesTable(rows, chosenId) {
    const body = document.getElementById("matchCandidatesBody");
    if (!body) return;

    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="6">No matches.</td></tr>`;
      return;
    }

    body.innerHTML = rows.map(it => {
      const checked = (it.id === chosenId) ? "checked" : "";
      const title = esc(it.title);
      const cost = (it.cost_total ?? 0).toFixed(2);
      const sku = esc(it.sku || "");
      const loc = esc(it.location || "");
      const status = esc(it.status || "");
      return `
        <tr>
          <td>
            <input type="radio" name="matchPick" value="${it.id}" ${checked} class="js-match-pick" data-item-id="${it.id}">
          </td>
          <td><b>${title}</b><div class="small">${esc(it.acquired_date || "")}</div></td>
          <td>$${cost}</td>
          <td>${sku || "<span class='small'>—</span>"}</td>
          <td>${loc || "<span class='small'>—</span>"}</td>
          <td>${status}</td>
        </tr>
      `;
    }).join("");
  }

  window.InventoryRender = {
    esc,
    setStatus,
    setResult,
    openMiniWindow,
    renderUnmatchedSalesTable,
    renderNeedsSplitTable,
    renderUnlistedTable,
    renderMatchCandidatesTable,
  };
})();

