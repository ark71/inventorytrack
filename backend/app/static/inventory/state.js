// static/inventory/state.js
(function () {
  "use strict";

  const State = {
    activeTab: "needs_split",

    // needs_split containers cached by id
    needsSplitById: {},

    // unmatched sales cached by id
    unmatchedSalesById: {},

    // match dialog state
    currentSaleToMatchId: null,
    currentChosenInventoryId: null,

    // candidate inventory cache for matching (loaded on demand)
    candidateInventoryCache: null,
  };

  window.InventoryState = State;
})();

