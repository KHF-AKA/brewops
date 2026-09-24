# API reference

All endpoints are defined in `src/brewops/api/main.py`. JSON in, JSON out.

## `GET /api/stats`
Dashboard numbers. Optional query params: `start` and `end` in `YYYY-MM-DD` format
for a date range (both inclusive). If neither is given, returns all-time data. Both
are optional independently (e.g., `?start=2026-06-01` for "from this date onward").
Returns 400 if dates are malformed or if `start` is after `end`.

Example: `GET /api/stats?start=2026-06-01&end=2026-06-30` filters to June 2026.

Response:
```json
{
  "total_brews": 2581,
  "per_drink": [{"name": "espresso", "label": "Espresso", "count": 1044}, ...],
  "per_day": [{"day": "2026-06-01", "count": 42}, ...]
}
```

## `GET /api/machines`
Returns the fleet: `[{"id", "name", "floor", "has_telemetry"}, ...]`.

## `GET /api/machines/{machine_id}`
The machine health card. Optional query params: `start` and `end` in `YYYY-MM-DD`
format for a date range (both inclusive). If neither is given, returns all-time data.
Returns 400 if dates are malformed or if `start` is after `end`. Returns 404 if the
machine id doesn't exist.

Returns machine fields plus:
```json
{
  "brew_count": 2581,
  "last_brew": "2026-07-04 11:14:00",
  "last_maintenance": {"type": "refill", "timestamp": "...", "note": "...", "error_code": null} | null,
  "recent_errors": [{"timestamp": "...", "error_code": "E42", "note": "..."}, ...],
  "specialty": {"name": "espresso", "label": "Espresso", "count": 1044, "last_brewed": "..."} | null,
  "usage_by_weekday": [{"weekday": "Mon", "count": 472}, ..., {"weekday": "Sun", "count": 20}]
}
```
- `specialty` is the most-brewed drink for that machine (ties broken by most
  recent brew); `null` if the machine has no brews yet.
- `usage_by_weekday` is always 7 entries, Monday-first, zero-filled.
- `recent_errors` is the 5 most recent `maintenance_events` rows of type
  `error`; `last_maintenance` is the most recent row of any other type.

## `GET /api/drink-types`
Returns the drink menu: `[{"id", "name", "label"}, ...]`.

## `POST /api/brews`
Body:
```json
{"machine_id": 1, "drink_type": "espresso", "timestamp": "2026-06-05T14:30", "duration_s": 27.5, "temp_c": 92.0}
```
`duration_s`/`temp_c` are optional. `timestamp` accepts either
`YYYY-MM-DD HH:MM:SS` or the HTML `datetime-local` format
`YYYY-MM-DDTHH:MM[:SS]`. Always inserted with `source='manual'`.

400 with a `detail` message for: unknown `machine_id`, unknown `drink_type`,
unparsable timestamp, or a future timestamp.

Response: `{"id": <brew_id>, "status": "logged"}`.

## `POST /api/maintenance`
Body:
```json
{"machine_id": 1, "type": "descale", "timestamp": "2026-06-06 09:00:00", "note": "...", "error_code": null}
```
`type` must be one of `descale`, `refill`, `repair`, `error`. Same timestamp
rules and 400 behavior as `/api/brews`.

Response: `{"id": <event_id>, "status": "logged"}`.

## Static frontend
Everything under `/` (not `/api/*`) is served from `src/brewops/frontend/` as
static files (`index.html`, `app.js`, `style.css`).
