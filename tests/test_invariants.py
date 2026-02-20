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


def test_split_invariant_sum_equals_container():
    conn = _make_conn()

    cur = conn.execute(
        """
        INSERT INTO inventory_items (title, status, cost_total, cost_method, sku)
        VALUES (?, 'needs_split', 32.67, 'exact_line', ?)
        """,
        ("Container", "GW-TESTINV"),
    )
    container_id = cur.lastrowid

    titles = "\n".join(
        [
            "Locked A | 10.00",
            "Locked B | 5.00",
            "U1",
            "U2",
            "U3",
        ]
    )

    res = split_with_titles(conn, container_id, titles)
    assert res["ok"] is True, res

    # verify totals balance exactly
    row = conn.execute(
        """
        SELECT ROUND(COALESCE(SUM(cost_total), 0), 2) AS s
        FROM inventory_items
        WHERE parent_inventory_item_id = ?
        """,
        (container_id,),
    ).fetchone()
    assert float(row["s"]) == 32.67
