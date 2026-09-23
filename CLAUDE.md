# BrewOps

Telemetry app for the office coffee machines. Python with FastAPI, data in SQLite
(stdlib `sqlite3`, no ORM).

## Architecture

```
CSV inbox ──┐
            ├─▶ ingest ──▶ db (SQLite) ──▶ api (FastAPI) ──▶ frontend (vanilla JS)
manual form ┘
```

- `src/brewops/db/` — schema (`schema.py`), reference data (machines, drink types),
  and all read/write SQL (`queries.py`). This is the only layer that touches SQL.
- `src/brewops/ingest/` — CSV loader (`loader.py`) plus the `uv run ingest` /
  `uv run seed` CLI entry points (`cli.py`).
- `src/brewops/api/main.py` — one FastAPI app: JSON endpoints under `/api/*`, and it
  also mounts `frontend/` as static files, so the whole thing is a single process.
- `src/brewops/frontend/` — no build step, no framework. Plain HTML/CSS/JS, fetches
  the `/api/*` endpoints directly.

## Two ways brews get recorded

1. **CSV ingestion** (`ingest/loader.py`) — files dropped in an inbox folder
   (`data/inbox` by default), named by convention:
   - `brews_*.csv` → brew events, `source='csv'`
   - `manual_*.csv` → brew events, `source='manual'` (exports of the paper log kept
     next to Old Faithful, the one machine with `has_telemetry=false`)
   - `maintenance_*.csv` → maintenance events
   Unrecognized filenames are skipped; bad rows are rejected and reported, but the
   rest of the file still loads. Run with `uv run ingest [path]`.
2. **Manual entry via the UI** — the dashboard's brew/maintenance forms POST to
   `/api/brews` / `/api/maintenance`, which insert with `source='manual'` directly.

Both paths converge on the same `brew_events` / `maintenance_events` tables and the
same validation rules (known machine, known drink type, timestamp not in the future).

## Running and testing

- `uv run start` — serve the app at http://localhost:8123.
- `uv run seed` — wipe and rebuild the DB from `data/inbox`.
- `uv run pytest` — run the test suite (`tests/`). No `httpx`/`starlette.testclient`
  dependency by design; API tests drive the ASGI app directly via the minimal client
  in `tests/asgi_client.py`. DB tests use a temp SQLite file via the `conn` fixture.

## Conventions

- Timestamps are always naive local time, stored as `'YYYY-MM-DD HH:MM:SS'` strings
  — no timezone handling anywhere. The API also accepts the HTML datetime-local form
  (`YYYY-MM-DDTHH:MM`) and normalizes it.
- `drink_type` is a free-standing TEXT key (not an integer FK) referencing
  `drink_types.name` — both `brew_events` and the ingest CSVs use the machine-readable
  name (e.g. `espresso`), while `label` (e.g. `Espresso`) is display-only.
- All SQL lives in `db/queries.py`; the API layer never writes raw SQL.
- `GET /api/machines/{id}` returns one aggregate "health" dict (brew count, last
  brew, last maintenance, recent errors, specialty) built from several queries in
  `get_machine_health` — this is the shape the frontend's machine cards consume
  directly, so new per-machine stats belong there.
- `$BREWOPS_DB` overrides the SQLite file path (used by tests); defaults to
  `./brewops.db`.
