# Codebase Task Proposals

## 1) Typo cleanup task
**Issue:** A stale inline comment reads `# if you have this service`, which looks like leftover scaffolding text in production code and can confuse maintainers.

**Proposed task:** Remove or rewrite the comment to a neutral description (e.g., `# eBay sold CSV import service`).

**Location:** `backend/app/routes/api_imports.py`

---

## 2) Bug fix task
**Issue:** `backend/app/routes/api_inventory.py` defines the same route (`POST /api/inventory/manual`) twice and both implementations call `get_conn()`, which is not defined in this module. This can raise a runtime `NameError` and also makes handler behavior ambiguous.

**Proposed task:** Consolidate to one `POST /api/inventory/manual` handler, replace `get_conn()` with `db_connect()`, and remove dead placeholder code and duplicate route registration.

**Location:** `backend/app/routes/api_inventory.py`

---

## 3) Comment/docs discrepancy task
**Issue:** UI guidance says to keep all CSS in `app.css` and avoid inline styles, but templates currently contain many inline `style="..."` attributes.

**Proposed task:** Move repeated inline styles into semantic CSS classes in `backend/app/static/app.css` and update templates to use those classes.

**Locations:** `docs/UI_DESIGN_SYSTEM.txt`, `backend/app/templates/imports.html` (and similar templates)

---

## 4) Test improvement task
**Issue:** Existing tests focus on monetary utilities/import/schema checks, but there is no API test coverage for the manual inventory endpoint path where the duplicate-route/undefined-connection bug exists.

**Proposed task:** Add API-level tests for `POST /api/inventory/manual` using FastAPI `TestClient`, including:
- success path with minimal payload,
- invalid payload handling,
- regression assertion that handler does not raise `NameError` due to missing connection helper.

**Locations:** `tests/` suite (new API route test module), `backend/app/routes/api_inventory.py`
