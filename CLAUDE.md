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
# one-time setup (creates C:\python_env\venv and installs requirements.txt)
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
  `routes_listing.py`, `routes_pricing_v2.py`, `routes_catalog_v2.py`, `routes_admin.py`,
  `routes_blacklist.py`, `routes_account.py`, `routes_oauth.py`, `routes_shipping.py`,
  `routes_override_seller.py`, `routes_status_engine.py`). Background loops call functions in these
  modules directly (e.g. `update_home_pricing`, `update_region_pricing`, `update_listing_price` from
  `routes_pricing_v2.py`) rather than going over HTTP.
- `adapters/` — SP-API request adapters. Consistently split into **HOME** (seller's home
  marketplace, JP) vs **REGION** (the target foreign marketplace) variants, e.g.
  `catalog_adapter_home.py` / `catalog_adapter_region.py`, `pricing_adapter_home.py` /
  `pricing_adapter_region.py`. This home/region duality runs throughout the codebase (DB columns,
  TTL settings, background loop logic) — always check whether a change needs to apply to both sides.
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

- `amazon/db.py` is the single connection entry point (`get_conn(db_name)`). It supports two modes
  via `ZSSS_DB_MODE` in `.env`: `sqlite` (file-per-concern under `db/`, e.g. `a_marketplaces.db`,
  `a_pricing_cache.db`, `a_<region>_listed_items.db`) or `postgres` (single DB via `PG_HOST` /
  `PG_PORT` / `PG_USER` / `PG_PASSWORD` / `PG_DATABASE`). **The codebase is mid-migration from SQLite
  to Postgres** — schema in `db_migrate.py` is written Postgres-style (`SERIAL PRIMARY KEY`) and many
  queries already use `%s` placeholders (psycopg2 style); `sqlite_to_postgres.py` at the repo root is
  the one-off migration script. When touching DB code, check `DB_MODE` assumptions rather than
  assuming SQLite's `?` placeholder style.
- DB filenames follow an `a_<region>_<purpose>.db` convention (legacy convention from
  `reference/zsss_webフォルダ構成.txt`: Amazon-related files/scripts are prefixed `a_`, and
  region-specific CSV/output files are prefixed with the region code, e.g. `AU_...`).
- `db/` holds live runtime DBs and is gitignored; `db_old/` is a snapshot of the pre-migration SQLite
  files kept for reference, not used by the app.
- `_resolve_db_path()` special-cases DB names containing `_blacklist_` (→ `db/blacklist/`) and
  `_seller_list` (→ `db/sellerlist/`).

## Environment

`.env` (gitignored) configures: `ZSSS_DB_MODE` (`sqlite`|`postgres`), `PG_HOST`/`PG_PORT`/`PG_USER`/
`PG_PASSWORD`/`PG_DATABASE`, `FX_API_KEY`. `python-dotenv` loads it in both `amazon/db.py` and
`amazon/background/fx/fx_loop.py`.
