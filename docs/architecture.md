# Architecture

```
CSV inbox ──┐
            ├─▶ ingest ──▶ db (SQLite) ──▶ api (FastAPI) ──▶ frontend (vanilla JS)
manual form ┘
```

One process, one port (8123): FastAPI serves both the JSON API and the static
frontend.

## Layers

- **`src/brewops/db/`** — `schema.py` (table definitions + reference data) and
  `queries.py` (all read/write SQL). This is the only layer that touches SQL —
  see [conventions.md](conventions.md).
- **`src/brewops/ingest/`** — `loader.py` (CSV parsing/validation/loading) and
  `cli.py` (the `uv run ingest` / `uv run seed` entry points). See
  [ingestion.md](ingestion.md).
- **`src/brewops/api/main.py`** — the FastAPI app. Defines every `/api/*`
  endpoint and mounts `src/brewops/frontend/` as static files at `/`. See
  [reference/api.md](reference/api.md).
- **`src/brewops/frontend/`** — plain HTML/CSS/JS, no build step, no
  framework. Fetches `/api/*` directly with the browser's `fetch`.

## Request flow example: the machine health card

1. Frontend (`app.js`, `loadDashboard`) fetches `/api/machines`, then fetches
   `/api/machines/{id}` for each machine.
2. API (`main.py`, `machine_health`) calls `queries.get_machine_health`.
3. DB layer runs several queries against `brew_events` / `maintenance_events`
   and bundles the results into one dict (brew count, last brew, last
   maintenance, recent errors, specialty, usage by weekday).
4. Frontend renders that dict directly into a card (`renderMachineCards`).

New per-machine stats generally follow this same pattern: add a query, fold
its result into `get_machine_health`, render it in `renderMachineCards`. No
API change is needed since the endpoint just passes the dict through.
