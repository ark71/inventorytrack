import sqlite3

from backend.app.utils.money import money_to_cents
from backend.app.services.split import split_with_titles


def test_money_to_cents():
    assert money_to_cents("10") == 1000
    assert money_to_cents("10.00") == 1000
    assert money_to_cents("$9.99") == 999


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(
        """
        CREATE TABLE inventory_items (
            id INTEGER PRIMARY KEY,
            purchase_line_id INTEGER,
            title TEXT NOT NULL,
            category TEXT,
            condition TEXT,
            quantity INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'unlisted',
            sku TEXT,
            location TEXT,
            notes TEXT,
            cost_item_price REAL,
            cost_tax REAL,
            cost_fees REAL,
            cost_shipping REAL,
            cost_handling REAL,
            cost_donation REAL,
            cost_total REAL,
            cost_method TEXT,
            acquired_date TEXT,
            attributes_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT,
            parent_inventory_item_id INTEGER
        );
        """
    )
    return conn


def test_split_with_titles_balances_to_container_total():
    conn = _make_conn()

    # Create a container worth $10.00
    cur = conn.execute(
        """
        INSERT INTO inventory_items (title, quantity, status, cost_total, cost_method)
        VALUES ('Test Container', 1, 'needs_split', 10.00, 'exact_line')
        """
    )
    container_id = cur.lastrowid

    # 3 children, all unlocked -> should allocate 3.34, 3.33, 3.33 (or equivalent)
    res = split_with_titles(conn, container_id, "A\nB\nC\n")
    assert res["ok"] is True
    assert res["inserted_children"] == 3

    # Sum children == container total (to cents)
    row = conn.execute(
        "SELECT ROUND(SUM(cost_total), 2) AS s FROM inventory_items WHERE parent_inventory_item_id=?",
        (container_id,),
    ).fetchone()
    assert float(row["s"]) == 10.00


def test_split_with_locked_costs():
    conn = _make_conn()

    cur = conn.execute(
        """
        INSERT INTO inventory_items (title, quantity, status, cost_total, cost_method)
        VALUES ('Test Container', 1, 'needs_split', 10.00, 'exact_line')
        """
    )
    container_id = cur.lastrowid

    # A locked at 4.00, remaining 6.00 split across 2 => 3.00 and 3.00
    res = split_with_titles(conn, container_id, "A | 4.00\nB\nC\n")
    assert res["ok"] is True, res

    # Pull child costs
    kids = conn.execute(
        "SELECT title, ROUND(cost_total, 2) AS c FROM inventory_items WHERE parent_inventory_item_id=? ORDER BY id",
        (container_id,),
    ).fetchall()
    costs = [float(k["c"]) for k in kids]

    assert 4.00 in costs
    assert costs.count(3.00) == 2
    assert round(sum(costs), 2) == 10.00

