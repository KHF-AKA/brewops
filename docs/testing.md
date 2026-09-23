# Running and testing

## Running

- `uv run start` — serve the app at http://localhost:8123 (API + frontend,
  one process).
- `uv run seed` — wipe and rebuild the DB from `data/inbox`. Run from the repo
  root (it looks for `./data/inbox`).
- `uv run ingest [path]` — ingest a CSV file or folder without resetting the
  DB first.

## Testing

- `uv run pytest` — runs everything under `tests/`. `pyproject.toml` sets
  `addopts = "-v --tb=short"`, so every test prints its name and pass/fail
  status by default, with a short traceback on failure.
- No `httpx` / `starlette.testclient` dependency, by design — API tests drive
  the ASGI app directly through the minimal client in `tests/asgi_client.py`.
- Every test has a one-line docstring stating the behavior it verifies — add
  one when writing a new test.
- DB/ingest tests get an isolated SQLite file via a `conn` fixture
  (`connect(tmp_path / "test.db")`); API/frontend tests additionally set
  `$BREWOPS_DB` via `monkeypatch` so the app under test uses that same file.

## Test files

| File | Covers |
|---|---|
| `tests/test_db.py` | `db/queries.py` and `db/schema.py` directly |
| `tests/test_api.py` | every `/api/*` endpoint, via `asgi_client.request(app, ...)` |
| `tests/test_frontend.py` | static file serving, no external resources |
| `tests/test_ingest.py` | CSV parsing/validation/loading |
