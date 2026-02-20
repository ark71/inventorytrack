from __future__ import annotations

import sqlite3

from backend.app.services.split import split_with_titles


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.executescript(
        """
        CREATE TABLE inventory_items (
          id                       INTEGER PRIMARY KEY,
          purchase_line_id         INTEGER,
          title                    TEXT NOT NULL,
          category                 TEXT,
          "condition"              TEXT,
          quantity                 INTEGER NOT NULL DEFAULT 1,
          status                   TEXT NOT NULL DEFAULT 'unlisted',
          sku                      TEXT,
          location                 TEXT,
          notes                    TEXT,
          cost_item_price          REAL,
          cost_tax                 REAL,
          cost_fees                REAL,
          cost_shipping            REAL,
          cost_handling            REAL,
          cost_donation            REAL,
          cost_total               REAL,
          cost_method              TEXT,
          acquired_date            TEXT,
          attributes_json          TEXT,
          created_at               TEXT NOT NULL DEFAULT (datetime('now')),
          updated_at               TEXT,
          parent_inventory_item_id INTEGER
        );
        CREATE UNIQUE INDEX idx_inventory_sku_unique
        ON inventory_items(sku) WHERE sku IS NOT NULL;
        """
    )
    return conn


def test_split_with_titles_balances_to_container_total():
    conn = _make_conn()

    cur = conn.execute(
        """
        INSERT INTO inventory_items (title, quantity, status, cost_total, cost_method, sku)
        VALUES ('Test Container', 1, 'needs_split', 10.00, 'exact_line', 'GW-TMONEY')
        """
    )
    container_id = cur.lastrowid

    res = split_with_titles(conn, container_id, "A\nB\nC\n")
    assert res["ok"] is True, res

    # children must sum to 10.00 exactly
    row = conn.execute(
        """
        SELECT ROUND(COALESCE(SUM(cost_total), 0), 2) AS s
        FROM inventory_items
        WHERE parent_inventory_item_id = ?
        """,
        (container_id,),
    ).fetchone()
    assert float(row["s"]) == 10.00


def test_split_with_locked_costs():
    conn = _make_conn()

    cur = conn.execute(
        """
        INSERT INTO inventory_items (title, quantity, status, cost_total, cost_method, sku)
        VALUES ('Test Container', 1, 'needs_split', 10.00, 'exact_line', 'GW-TLOCKS')
        """
    )
    container_id = cur.lastrowid

    res = split_with_titles(conn, container_id, "A | 4.00\nB\nC\n")
    assert res["ok"] is True, res

    # A locked 4.00, remaining 6.00 split evenly => 3.00, 3.00
    rows = conn.execute(
        """
        SELECT title, cost_total
        FROM inventory_items
        WHERE parent_inventory_item_id = ?
        ORDER BY id
        """,
        (container_id,),
    ).fetchall()
    costs = {r["title"]: float(r["cost_total"]) for r in rows}
    assert costs["A"] == 4.00
    assert costs["B"] == 3.00
    assert costs["C"] == 3.00
