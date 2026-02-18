CREATE TABLE import_files (
  id            INTEGER PRIMARY KEY,
  source        TEXT NOT NULL,              -- 'shopgoodwill' | 'ebay_sold' | 'manual'
  filename      TEXT NOT NULL,
  file_sha256   TEXT,                       -- detect duplicates
  imported_at   TEXT NOT NULL DEFAULT (datetime('now')),
  notes         TEXT
);
CREATE INDEX idx_import_files_source_time
ON import_files(source, imported_at);
CREATE TABLE purchases (
  id                INTEGER PRIMARY KEY,
  source            TEXT NOT NULL,           -- 'shopgoodwill', 'thrift', 'garage_sale', 'personal', etc.
  order_number      TEXT,                    -- ShopGoodwill "Order #"; nullable for non-order purchases
  order_date        TEXT,                    -- ShopGoodwill "Order Date" (ISO string preferred)
  seller            TEXT,                    -- ShopGoodwill "Seller" or store name
  notes             TEXT,

  -- totals (can be computed from lines during import)
  payment_date      TEXT,                    -- ShopGoodwill "Payment Date"
  payment_amount    REAL,                    -- ShopGoodwill "Payment Amount"
  tax_total         REAL,
  additional_fee_total REAL,
  shipping_total    REAL,
  handling_total    REAL,
  donation_total    REAL,
  total             REAL,                    -- optional convenience

  import_file_id    INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
  raw_order_json    TEXT,                    -- preserve order snapshot
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(source, order_number)
);
CREATE INDEX idx_purchases_source_date
ON purchases(source, order_date);
CREATE TABLE purchase_lines (
  id              INTEGER PRIMARY KEY,
  purchase_id     INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,

  -- ShopGoodwill headers (verbatim retained in columns)
  item_id         TEXT,        -- "Item Id"
  item_name       TEXT,        -- "Item"
  category        TEXT,        -- "Category"
  quantity        INTEGER,     -- "Quantity"
  item_price      REAL,        -- "Item Price"
  item_end_time   TEXT,        -- "Item End Time"
  tracking_number TEXT,        -- "Tracking #"
  tax             REAL,        -- "Tax"
  additional_fee  REAL,        -- "Additional Fee"
  shipping_price  REAL,        -- "Shipping Price"
  handling_price  REAL,        -- "Handling Price"
  donation        REAL,        -- "Donation"
  shipped_date    TEXT,        -- "Shipped Date"

  -- internal helpers
  raw_row_json    TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(purchase_id, item_id)
);
CREATE INDEX idx_purchase_lines_purchase
ON purchase_lines(purchase_id);
CREATE TABLE inventory_items (
  id                INTEGER PRIMARY KEY,

  -- linkage to source purchase line (optional but ideal)
  purchase_line_id  INTEGER REFERENCES purchase_lines(id) ON DELETE SET NULL,

  -- core fields
  title             TEXT NOT NULL,
  category          TEXT,
  condition         TEXT,
  quantity          INTEGER NOT NULL DEFAULT 1,  -- for multi-qty items
  status            TEXT NOT NULL DEFAULT 'unlisted',
  -- suggested statuses: unlisted, listed, sold, shipped, returned, removed

  sku               TEXT,                        -- your internal label
  location          TEXT,                        -- bin/shelf/etc.
  notes             TEXT,

  -- cost basis (what matters for profit)
  cost_item_price   REAL,                        -- base item cost
  cost_tax          REAL,
  cost_fees         REAL,                        -- buyer premium/additional fees, etc.
  cost_shipping     REAL,
  cost_handling     REAL,
  cost_donation     REAL,
  cost_total        REAL,                        -- convenience (can be computed)
  cost_method       TEXT,                        -- 'exact', 'allocated', 'manual'

  acquired_date     TEXT,                        -- default from purchase/order date
  attributes_json   TEXT,                        -- future-proof (brand, model, size, etc.)

  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT
, parent_inventory_item_id INTEGER REFERENCES inventory_items(id));
CREATE UNIQUE INDEX idx_inventory_sku_unique
ON inventory_items(sku) WHERE sku IS NOT NULL;
CREATE INDEX idx_inventory_status
ON inventory_items(status);
CREATE INDEX idx_inventory_purchase_line
ON inventory_items(purchase_line_id);
CREATE TABLE listings (
  id            INTEGER PRIMARY KEY,
  platform      TEXT NOT NULL,            -- 'ebay' (future: 'fbm', 'poshmark', etc.)
  listing_key   TEXT,                     -- eBay Item Number (if you have it later), or any platform ID
  title         TEXT,
  status        TEXT NOT NULL DEFAULT 'draft',
  -- draft, active, ended, sold

  created_date  TEXT,
  ended_date    TEXT,

  price         REAL,
  currency      TEXT,

  notes         TEXT,
  raw_json      TEXT,

  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT,

  UNIQUE(platform, listing_key)
);
CREATE INDEX idx_listings_platform_status
ON listings(platform, status);
CREATE TABLE listing_items (
  listing_id       INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
  qty_in_listing   INTEGER NOT NULL DEFAULT 1,

  PRIMARY KEY (listing_id, inventory_item_id)
);
CREATE INDEX idx_listing_items_item
ON listing_items(inventory_item_id);
CREATE TABLE ebay_orders (
  id INTEGER PRIMARY KEY,

  order_number TEXT NOT NULL,
  order_creation_date TEXT,

  buyer_name TEXT,
  ship_to_city TEXT,
  ship_to_region_state TEXT,
  ship_to_zip TEXT,
  ship_to_country TEXT,

  transaction_currency TEXT,
  payout_currency TEXT,

  ebay_collected_tax REAL,
  seller_collected_tax REAL,

  gross_amount REAL,
  expenses REAL,
  refunds REAL,
  order_earnings REAL,
  your_cost REAL,
  net_order_earnings REAL,

  final_value_fee_fixed REAL,
  final_value_fee_variable REAL,
  below_standard_performance_fee REAL,
  very_high_inad_fee REAL,
  international_fee REAL,
  deposit_processing_fee REAL,
  regulatory_operating_fee REAL,
  promoted_listing_standard_fee REAL,
  charity_donation REAL,
  shipping_labels REAL,
  payment_dispute_fee REAL,

  import_file_id INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
  raw_order_json TEXT,
  imported_at TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(order_number)
);
CREATE INDEX idx_ebay_orders_date
ON ebay_orders(order_creation_date);
CREATE TABLE ebay_order_items (
  id INTEGER PRIMARY KEY,
  ebay_order_id INTEGER NOT NULL REFERENCES ebay_orders(id) ON DELETE CASCADE,

  item_id TEXT,                 -- "Item ID" (from the sold CSV)
  item_title TEXT,
  quantity INTEGER,

  item_price REAL,
  item_subtotal REAL,
  shipping_and_handling REAL,
  discount REAL,

  -- optional linkage if/when you also import listing item numbers
  listing_id INTEGER REFERENCES listings(id) ON DELETE SET NULL,

  raw_row_json TEXT,
  imported_at TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(ebay_order_id, item_id, item_title)
);
CREATE INDEX idx_ebay_order_items_order
ON ebay_order_items(ebay_order_id);
CREATE TABLE sale_links (
  id INTEGER PRIMARY KEY,
  ebay_order_item_id INTEGER NOT NULL REFERENCES ebay_order_items(id) ON DELETE CASCADE,
  inventory_item_id  INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE RESTRICT,
  qty                INTEGER NOT NULL DEFAULT 1,

  created_at         TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(ebay_order_item_id, inventory_item_id)
);
CREATE INDEX idx_sale_links_inventory
ON sale_links(inventory_item_id);
CREATE UNIQUE INDEX ux_purchases_source_order

ON purchases(source, order_number);
CREATE UNIQUE INDEX ux_purchase_lines_purchase_item

ON purchase_lines(purchase_id, item_id);
