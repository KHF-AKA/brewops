# Ingestion

Brews get into the database two ways. Both converge on the same
`brew_events` / `maintenance_events` tables and the same validation rules
(known machine, known drink type, timestamp not in the future).

## 1. CSV ingestion (`src/brewops/ingest/loader.py`)

Files dropped in an inbox folder (`data/inbox` by default), named by
convention — the loader reads the filename prefix to decide what a file is:

| Filename prefix | Loaded as | `source` |
|---|---|---|
| `brews_*.csv` | brew events | `csv` |
| `manual_*.csv` | brew events | `manual` (exports of the paper log kept next to Old Faithful, the one machine with `has_telemetry=false`) |
| `maintenance_*.csv` | maintenance events | — |

Anything else is skipped entirely (reported, not an error). Within a
recognized file, bad rows are rejected individually and reported — the rest
of the file still loads.

Columns:
- brew files: `machine_id, drink, timestamp, duration_s, temp_c`
- maintenance files: `machine_id, type, timestamp, note, error_code`

Run with `uv run ingest [path]` (defaults to `data/inbox`; accepts a single
file or a directory — directories are processed in sorted filename order for
determinism). `uv run seed` wipes the DB and re-ingests `data/inbox` from
scratch.

## 2. Manual entry via the UI

The dashboard's brew/maintenance forms (`index.html` + `app.js`) POST to
`/api/brews` / `/api/maintenance` (see [reference/api.md](reference/api.md)),
which insert with `source='manual'` directly — no CSV involved. This is the
only way brews get recorded for machines without telemetry.

## Adding a new drink type

Don't hand-edit this by touching `schema.py`/`queries.py`/`app.js`
separately — use the `add-drink-type` skill, which wires a new drink through
validation, the dashboard dropdowns, and stats in one pass.
