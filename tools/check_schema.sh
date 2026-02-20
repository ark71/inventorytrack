#!/usr/bin/env bash
set -euo pipefail

echo "== Regenerating create_db_full.py from schema_from_working_db.sql =="
./tools/generate_create_db_full.py

echo "== Verifying create_db.py can build a fresh DB =="
python3 create_db.py --db /tmp/it_schema_check.db --force --verify
sqlite3 /tmp/it_schema_check.db ".schema sales" >/dev/null

echo "== Verifying create_db_full.py can build a fresh DB =="
python3 create_db_full.py --db /tmp/it_schema_full_check.db --force
sqlite3 /tmp/it_schema_full_check.db ".schema sales" >/dev/null

echo "✅ Schema regen + DB creation checks passed."

