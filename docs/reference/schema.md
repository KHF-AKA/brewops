# Database schema

SQLite, stdlib `sqlite3`, no ORM. Defined in `src/brewops/db/schema.py`.

## Tables

```sql
machines (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    floor         INTEGER NOT NULL,
    has_telemetry INTEGER NOT NULL DEFAULT 1
)

drink_types (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE,   -- machine-readable key, e.g. "espresso"
    label TEXT NOT NULL           -- display text, e.g. "Espresso"
)

brew_events (
    id         INTEGER PRIMARY KEY,
    machine_id INTEGER NOT NULL REFERENCES machines(id),
    drink_type TEXT NOT NULL REFERENCES drink_types(name),
    timestamp  TEXT NOT NULL,     -- 'YYYY-MM-DD HH:MM:SS', naive local time
    duration_s REAL,
    temp_c     REAL,
    source     TEXT NOT NULL CHECK (source IN ('csv', 'manual'))
)

maintenance_events (
    id         INTEGER PRIMARY KEY,
    machine_id INTEGER NOT NULL REFERENCES machines(id),
    type       TEXT NOT NULL CHECK (type IN ('descale', 'refill', 'repair', 'error')),
    timestamp  TEXT NOT NULL,
    note       TEXT,
    error_code TEXT
)
```

Indexes: `brew_events(machine_id)`, `brew_events(timestamp)`,
`maintenance_events(machine_id)`.

## Seeded reference data

The fleet (`MACHINES` in `schema.py`) — fixed, not user-editable via the API:

| id | name | floor | has_telemetry |
|---|---|---|---|
| 1 | Bertha (3rd floor) | 3 | true |
| 2 | The Intern (kitchen) | 1 | true |
| 3 | Old Faithful (2nd floor) | 2 | false — brews logged manually |
| 4 | Rocket (4th floor) | 4 | true |

The drink menu (`DRINK_TYPES` in `schema.py`):

`espresso`, `lungo`, `cappuccino`, `latte`, `americano`, `hot_water`

`init_db` inserts both with `INSERT OR IGNORE`, so it's safe to call
repeatedly. `reset_db` drops `brew_events`/`maintenance_events`/`drink_types`/
`machines` and re-runs `init_db` — used by `uv run seed`.
