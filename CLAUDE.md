# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ZSSS Tools — a Flask web app for managing a cross-border Amazon reselling operation via the Amazon
Selling Partner API (SP-API). It handles multi-account/multi-marketplace catalog and pricing sync,
listing submission, blacklist management, shipping-rate calculation, and related DHL/PDF tooling.
Markets in use: JP (home) plus AU/US/SG/CA (target regions). UI and code comments are in Japanese.

This is a solo/small-team internal tool, not a published package — there is no test suite and no
linter/formatter config in the repo.

## Running the app

```bash
# one-time setup (creates ..\python_env\venv, i.e. a sibling of the repo folder, and installs requirements.txt)
setup_venv.bat

# run the dev server (activates the venv, then `python app.py`)
start_zsss_v2.bat
# equivalent manually:
python app.py [dev|zsss|atlas]
```

- The optional CLI arg (`dev`/`zsss`/`atlas`) selects which physical machine/environment is running
  and is stored in `app.config["ZSSS_MODE"]`; it's injected into every template as `zsss_mode`.
- The server listens on `0.0.0.0:5001` (see `app.py`), `debug=True`, `use_reloader=False` — the
  reloader is deliberately disabled because background threads are started once at process start.
- `update_requirements.bat` refreshes `requirements.txt` from the active venv via `pip freeze`.

There is no test runner, lint, or build/watch step configured — verify changes by running the app
and exercising the relevant route(s) in a browser, or by reading through the affected DB
queries/adapters directly.

## Architecture

### Entry point and startup sequence (`app.py`)

On `__main__`, in order: run `amazon.db_migrate.main()` to (re)create/patch DB schema, then start four
daemon background threads (`first`, `first_regioncheck`, `ttl`, `fx` — see below), attach a rotating
error log handler (`app_error.log`), then start Flask. All feature areas are registered as Blueprints
in `app.py` (amazon core, oauth, blacklist, dhl/pdf tools, csv import, listing, auth, account,
override_seller, admin/admin_market, api_raw_check, shipping, pricing_v2).

### `amazon/` — core module

- `routes/` — Flask blueprints, one per feature area (`routes.py` = marketplace/account master,
  `routes_listing.py`, `routes_pricing_v2.py`, `routes_catalog_v2.py`, `routes_admin.py` (exports
  both `admin_api_bp` and `admin_market_bp`), `routes_blacklist.py`, `routes_account.py`,
  `routes_oauth.py`, `routes_shipping.py`, `routes_override_seller.py`). Background loops call
  functions in these modules directly (e.g. `update_home_pricing`, `update_region_pricing`,
  `update_listing_price` from `routes_pricing_v2.py`) rather than going over HTTP.
  `routes_status_engine.py` lives in this folder but is not a blueprint — it's a pure helper
  (`evaluate_status`) for deriving a listing's ACTIVE/INACTIVE status from pricing rules.
- `amazon/csv_import.py` (registered as `csv_import_bp`, top-level `amazon/`, not under `routes/`) —
  CSV → ASIN/SKU import into `listed_items` tables. Assumes `db_migrate.py` has already created the
  target tables; does not create schema itself.
- `adapters/` — SP-API request adapters. Consistently split into **HOME** (seller's home
  marketplace, JP) vs **REGION** (the target foreign marketplace) variants, e.g.
  `catalog_adapter_home.py` / `catalog_adapter_region.py`, `pricing_adapter_home.py` /
  `pricing_adapter_region.py`. This home/region duality runs throughout the codebase (DB columns,
  TTL settings, background loop logic) — always check whether a change needs to apply to both sides.
- **Listing quantity (`update_listing_price` in routes_pricing_v2.py).** Normal items (出品数 OFF,
  `override_quantity` NULL) get a full PUT with `strategy_quantity` (1) on every TTL/refresh, so a
  sold-out offer comes back at the next cycle. Do NOT change this to price-only: AU runs on ATLAS
  with a separate DB, so ORBIT's 仕入済 relist can't reach it and AU items would stay at 0 forever.
  Only 出品数 ON items (`override_quantity` set) use the price-only PATCH (`patch_listings_item_price`),
  which leaves Amazon's decremented count alone. They're never relisted automatically (TTL, 仕入済,
  在庫0 OFF) — only when 出品数 is saved or turned OFF (`force_quantity`). ALL-Listing override routes
  must scope UPDATEs by `region_marketplace_id` (`_resolve_region_marketplace_id`), since
  `listed_items` holds every marketplace in one table.
- **重量区分 (`override_weight_class`) is per ASIN, not per marketplace.** Billable weight is the same
  wherever an item sells, so `update_shipping_override` writes every `listed_items` row of that ASIN and
  re-prices each country; CSV import copies an existing value to new rows of the same ASIN. (AU on ATLAS
  has its own DB, so it isn't reached from ZSSS.)
- **ORBIT 送料検証** (`services/orbit_ship_check_service.py`). `orbit_orders.est_*` freezes the
  predicted shipping fee / billable weight / carrier the first time an order is calculated, so later
  rate-table or weight-class edits don't rewrite the baseline. Never recompute or overwrite `est_*` once
  `est_snapshot_at` is set. Agent sheet S列 (`agent_shipping_fee`) equals the raw rate-table price; T列 is
  all-in. Carrier names for 送料表 Carrier 1–3 live in `shipping_carrier_names` (default DHL/FedEx/EMS).
  New ORBIT row keys must go in `_RAW_SHEET_SKIP_KEYS`, or ZSSS_RAW columns shift and VLOOKUPs break.
- **ORBIT 決済レポート** (`services/orbit_settlement_service.py`, buttons in subtab「利益分析」). Sales/fees/net
  proceeds come only from Settlement Report Flat File V2 (`orbit_settlements` + `orbit_settlement_items`), fetched via
  SP-API (`GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`, needs the 財務会計 role) or uploaded by hand (Seller Central
  wide format, API long format, or another environment's export). Each settlement is replaced whole by settlement-id,
  so re-imports never double-count; a settlement whose lines don't sum to its total is rejected. Lines join orders by
  `order_item_id`, so multi-item orders need no proration. API fetch runs per `ZSSS_MODE` (`SETTLEMENT_API_COUNTRIES`:
  zsss=US/CA, atlas=AU, dev=none) — never add AU to ZSSS; AU reaches ZSSS only as ATLAS's 決済データ書き出し file.
  getReportDocument allows ~1 call/min, so documents are downloaded 61s apart in a background thread without
  `user_id` (a 429 would otherwise block the user's other SP-API calls via guard_429). The old Transactions-CSV import
  (`orbit_settlement_lines`) is gone; don't bring it back (it double-counted 保留→入金済み rows).
- **ORBIT 成分台帳** (`services/orbit_ingredient_service.py`, subtab「成分台帳」). Per-ASIN 成分 text (FDA
  ingredients, battery type like アルカリ電池) that the shipping agent needs in 備考. Ledger ASINs get the text
  auto-appended to 備考1 (`remarks`) on order import and on ledger edit/delete/sheet import, only for orders with
  `shipped_completed` ≠ 1 (same freeze rule as the ZSSS_RAW push). Like the bundle note, the appended text is
  remembered in `ingredient_remarks_auto` and found/replaced later — never touch hand-written remarks.
  説明 (e.g. 発送不可) shows as a red warning next to the 「成」 mark in 発注管理. Can be imported from the old
  「FDA&電池関係」 Google Sheet (header row located by the 「ASIN」 cell).
- **その他ツール「文書管理」** (`tools/doc_library_routes.py` + `static/js/doc_library.js`). Buyer-message
  templates (category + title + body), copied from the screen and pasted into Amazon messages. Stored only in
  each environment's DB (運用PC is the real one; it's also what's opened from outside). Export/import is JSON
  (not CSV — Excel re-saves mangle bodies); import upserts by (category name, title) and never deletes. The copy
  button falls back to `execCommand` because remote access over plain http has no `navigator.clipboard`.
  英語マニュアル(PDF, ASIN/型番/JAN, multiple PDFs per item) is planned but parked until PDF storage is decided.
- **Pricing カテゴリ別手数料率 / カート取得状況** (`core/category_fee.py`, `services/buybox_stats_service.py`).
  Per country ON/OFF table that swaps `amazon_fee_rate` / `min_profit_rate` for listings whose catalog productType
  is in the table (built for year-end toys: AU 12%, CA 15%, min profit 0%). OFF countries and other types must price
  exactly as before, and a failure in the lookup falls back to the normal rules — never let it stop pricing. The user
  switches it ON themselves (CA on ZSSS, AU on ATLAS). カート取得状況 counts Buy Box share of LIVE listings from
  `pricing_cache.region_offers_json` (no SP-API calls); `background/buybox/buybox_loop.py` records it once a day
  (JST) into `buybox_daily_stats` so the effect of a price change can be compared before/after.
- `core/` — pricing business logic: `price_calculator.py`, `pricing_strategy.py`, `fx_rate.py`.
- `services/` — `blacklist_service.py`, `listing_submit_service.py`, `ttl_stop_service.py`.
- `background/` — long-running daemon loops started from `app.py`:
  - `first/first_loop.py`, `first/first_regioncheck.py` — initial/onboarding scan of newly listed
    items.
  - `ttl/ttl_loop.py`, `ttl/ttl_days.py` — periodic re-sync once an item's cached data expires (TTL
    thresholds and per-cycle limits are configurable via the `bg_scan_settings` DB table, columns
    defined in `db_migrate.py`).
  - `fx/fx_loop.py` — periodic currency exchange rate refresh (uses `FX_API_KEY` from `.env`).
  - `common/background_common.py` — shared helpers (e.g. discovering per-region `listed_items` DBs,
    API request pacing/sleep).
- `guard/` — SP-API error backoff: `guard_429.py` keeps an in-memory per-`(user_id, endpoint)`
  temporary block; `guard_404.py` permanently flags a specific ASIN (`api_stop_asin` column) as dead
  in the relevant `listed_items` table.
- `auth/token_manager.py` — SP-API LWA refresh-token handling (distinct from the top-level `auth/`
  Flask login blueprint).
- `spapi_client.py` — low-level AWS SigV4-style signed request builder for SP-API; picks
  `spapi_host` over `host` and derives the AWS region from the host string (`-na.`/`-eu.`/`-fe.`).
- `db.py` / `db_migrate.py` — see DB section below.

### Other top-level areas

- `auth/routes_auth.py` — session-based login (`session["user_id"]`), guarded by a `login_required`
  decorator; credentials are checked against the `a_user_login_accounts` table.
- `api_check/a_api_scan_allcheck.py` — ad hoc SP-API connectivity/permission check endpoint.
- `tools/` — `dhl_routes.py` (DHL rate/label tooling), `pdf_routes.py`.
- `static/`, `templates/` — plain Jinja2 + vanilla JS, no frontend build step. JS files generally
  pair 1:1 with a template (e.g. `templates/pricing.html` + `static/js/pricing.js`).

### Database

- `amazon/db.py` is the single connection entry point (`get_conn(db_name)`). **The codebase has been
  fully migrated off SQLite and is Postgres-only** (via `PG_HOST` / `PG_PORT` / `PG_USER` /
  `PG_PASSWORD` / `PG_DATABASE` in `.env`); `get_conn()` always connects to the single Postgres
  database and ignores the `db_name` argument's file-path shape — `db_name` (e.g.
  `"a_marketplaces.db"`, `"a_<region>_listed_items.db"`) is now purely a legacy label kept for call-site
  readability, not an actual file path. All queries use `%s` placeholders (psycopg2 style). The old
  SQLite-vs-Postgres dual-mode branching (`ZSSS_DB_MODE`, `_resolve_db_path()`, `_get_sqlite_conn()`)
  and the one-off `sqlite_to_postgres.py` migration script have been removed now that the migration is
  complete.
- DB filenames in `db_name` arguments still follow the legacy `a_<region>_<purpose>.db` naming
  convention (from `reference/zsss_webフォルダ構成.txt`, back when each concern was a separate SQLite
  file) purely as a naming convention for readability — they no longer resolve to real files.
- `db_old/` is a snapshot of the pre-migration SQLite files kept for reference, not used by the app.

## Environment

`.env` (gitignored) configures: `PG_HOST`/`PG_PORT`/`PG_USER`/`PG_PASSWORD`/`PG_DATABASE`,
`FX_API_KEY`. `python-dotenv` loads it in both `amazon/db.py` and `amazon/background/fx/fx_loop.py`.
