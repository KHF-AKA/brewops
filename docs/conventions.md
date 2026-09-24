# Conventions

- **Timestamps are always naive local time**, stored as `'YYYY-MM-DD HH:MM:SS'`
  strings — no timezone handling anywhere. The API also accepts the HTML
  `datetime-local` form (`YYYY-MM-DDTHH:MM`) and normalizes it
  (`parse_timestamp` in `api/main.py`). Future timestamps are rejected.
- **`drink_type` is a free-standing TEXT key**, not an integer FK — both
  `brew_events` and the ingest CSVs use the machine-readable name (e.g.
  `espresso`), while `drink_types.label` (e.g. `Espresso`) is display-only.
  See [reference/schema.md](reference/schema.md).
- **All SQL lives in `db/queries.py`**; the API layer (`api/main.py`) never
  writes raw SQL, only calls into `queries`.
- **`get_machine_health` is the machine-card aggregate.** `GET
  /api/machines/{id}` returns one dict — brew count, last brew, last
  maintenance, recent errors, specialty, usage by weekday — built from
  several queries in `get_machine_health`. This is the shape the frontend's
  machine cards consume directly, so a new per-machine stat belongs there,
  not a new endpoint. See [architecture.md](architecture.md).
- **Date-range filtering on time-scoped stats.** `GET /api/stats` and `GET
  /api/machines/{id}` both accept optional `start` and `end` query parameters
  in `YYYY-MM-DD` format (inclusive on both ends). Use `_range_clause` helper
  in `queries.py` to build the SQL fragment, and `parse_date_range` in
  `api/main.py` to parse and validate the dates. When adding a new per-machine
  or per-system stat, apply the same range if it's time-dependent.
- **`$BREWOPS_DB`** overrides the SQLite file path (used by tests to point at
  a temp file); defaults to `./brewops.db`.
- **No frontend build step, no framework, no external resources** — plain
  HTML/CSS/JS in `src/brewops/frontend/`, enforced by
  `test_frontend_has_no_external_resources`.
