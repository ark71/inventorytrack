from inventorytrack.create_db import _sanitize_schema_sql  # adjust import to your path

def test_sanitize_schema_strips_sqlite_sequence():
    sql = """
    BEGIN;
    CREATE TABLE foo(id INTEGER PRIMARY KEY);
    CREATE TABLE sqlite_sequence(name,seq);
    INSERT INTO sqlite_sequence VALUES('foo',1);
    COMMIT;
    """
    out = _sanitize_schema_sql(sql)
    assert "sqlite_sequence" not in out
    assert "CREATE TABLE foo" in out

