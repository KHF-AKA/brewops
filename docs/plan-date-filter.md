# Implementation plan: dashboard date-range filter

Implements [tickets/005-date-filter.md](../tickets/005-date-filter.md): let people pick a date range on
the dashboard and have all numbers and charts respect it.

This doc is written for an implementer with no prior context on this task. Read
[docs/architecture.md](architecture.md), [docs/conventions.md](conventions.md), and
[docs/reference/schema.md](reference/schema.md) first if anything below is unclear — those explain the
layers, the "all SQL lives in `db/queries.py`" rule, and the timestamp format.

Three decisions have already been made (don't re-litigate them):

1. Every field on the machine card, including `last_maintenance` and `recent_errors`, gets filtered by
   the date range — not just brew counts. If a range excludes an error, it simply won't show.
2. With no range picked, the dashboard shows all-time data — same as today. The filter is opt-in.
3. The "brews today" stat tile (`app.js` lines 109–110, computed from the last entry of
   `stats.per_day`) gets its **label** changed dynamically when a range filter is active — e.g.
   "Today" → "Last day in range" — instead of being hidden or left silently misleading. See section 5.

## 1. Files you will change

- `src/brewops/db/queries.py` — SQL changes (all query logic lives here, per project convention).
- `src/brewops/api/main.py` — new query params on two existing routes.
- `src/brewops/frontend/index.html` — two new date inputs.
- `src/brewops/frontend/app.js` — read/write the inputs, pass the range to the API.
- `docs/reference/api.md` — document the new query params.
- `docs/conventions.md` — note the range-filter convention for future per-machine stats.
- Tests under `tests/` (find the existing files that test `queries.py` and `main.py`, follow their
  pattern — see docs/testing.md).

Do not touch `src/brewops/frontend/style.css` unless the new inputs look broken; try reusing existing
`.form-panel input` / `.form-panel select` styles first.

## 2. Range semantics (apply this consistently everywhere)

- Two query parameters: `start` and `end`. Both optional. Format `YYYY-MM-DD` (date only, no time —
  this matches a native `<input type="date">`).
- Both days are fully inclusive. A brew on `end` at 23:59:59 must be included.
- Implement inclusivity by converting to a half-open range internally:
  - `start_bound = "<start> 00:00:00"`
  - `end_bound = "<end + 1 day> 00:00:00"` (i.e. add one calendar day to `end`, then midnight)
  - Then filter with `timestamp >= start_bound AND timestamp < end_bound`. Using `<` on a bound that's
    one day past `end` is what makes the last day fully inclusive without off-by-one bugs.
- `start` and `end` are independent — either can be omitted:
  - Neither given → no filtering at all (today's behavior).
  - Only `start` given → everything from `start` onward.
  - Only `end` given → everything up to and including `end`.
- If both are given and `start` is after `end` (i.e. `start_bound >= end_bound`), the API must reject
  the request with `HTTPException(400, ...)`. Do this validation in `main.py`, not in `queries.py`.
- Malformed date strings (anything `date.fromisoformat()` rejects) → also `HTTPException(400, ...)`.

## 3. Backend changes: `src/brewops/db/queries.py`

Add this helper near the top of the file, above the functions that use it:

```python
def _range_clause(column: str, start: str | None, end: str | None) -> tuple[str, list]:
    """Build an ' AND col >= ? AND col < ?'-style fragment (only for the bounds given)."""
    clauses, params = [], []
    if start is not None:
        clauses.append(f"{column} >= ?")
        params.append(start)
    if end is not None:
        clauses.append(f"{column} < ?")
        params.append(end)
    return (" AND ".join(clauses), params)
```

`start`/`end` passed into this helper (and into every function below) are already the resolved
`start_bound` / `end_bound` strings described in section 2 — that conversion happens in `main.py`, not
here. `queries.py` just receives two `str | None` values and treats them as ready-to-use
`>=` / `<` bounds.

Change these three functions, all in `queries.py`:

### `get_stats(conn)` → `get_stats(conn, start=None, end=None)`

Currently at line 68. It runs three separate queries — total, per-drink, per-day. All three need the
range applied, but **not the same way**:

- **Total** (`SELECT COUNT(*) ... FROM brew_events`): add a `WHERE <range clause>` if `start` or `end`
  is set. If neither is set, no `WHERE` at all (unchanged query).
- **Per-drink**: this one currently does a `LEFT JOIN` from `drink_types` to `brew_events` so that
  drink types with **zero** brews still show up with `count: 0`. This is important:
  **put the range clause inside the `ON` clause of the `LEFT JOIN`, not in a `WHERE`.**
  ```sql
  SELECT dt.name, dt.label, COUNT(be.id) AS count
  FROM drink_types dt
  LEFT JOIN brew_events be
    ON be.drink_type = dt.name AND be.timestamp >= ? AND be.timestamp < ?
  GROUP BY dt.id
  ORDER BY dt.id
  ```
  If you instead add the range as a `WHERE` clause after the join, SQLite effectively turns the outer
  join back into an inner join, and drink types with no brews in the range will silently disappear
  from the response instead of showing `count: 0`. This is the single easiest mistake to make in this
  task — verify it with the "drink type with zero brews in range" test case below.
- **Per-day** (`GROUP BY DATE(timestamp)`): plain `WHERE <range clause>` before the `GROUP BY` is fine
  here — there's no join, so no zero-count rows to preserve. A day with zero brews in the range simply
  does not appear as a row; that's correct, the frontend already only renders the days it's given.

### `get_machine_usage_by_weekday(conn, machine_id)` → `get_machine_usage_by_weekday(conn, machine_id, start=None, end=None)`

Currently at line 102. Add the range clause alongside the existing `WHERE machine_id = ?`. The
zero-fill logic that follows (turning missing weekdays into `count: 0`) needs no changes — it already
handles "this weekday has no rows" correctly; a narrow range just means more weekdays end up zero-filled.

### `get_machine_health(conn, machine_id)` → `get_machine_health(conn, machine_id, start=None, end=None)`

Currently at line 120. This function runs four separate queries internally, then calls
`get_machine_usage_by_weekday`. Apply the range to **all of them** (per decision #1 above):

- `brews` (count + `MAX(timestamp)` as `last_brew`) — add range to its `WHERE machine_id = ?`.
- `last_maintenance` — add range to its `WHERE machine_id = ? AND type != 'error'`.
- `recent_errors` — add range to its `WHERE machine_id = ? AND type = 'error'`.
- `specialty` (most-brewed drink) — add range to its `WHERE be.machine_id = ?`.
- The call to `get_machine_usage_by_weekday(conn, machine_id)` at the end — change it to
  `get_machine_usage_by_weekday(conn, machine_id, start, end)`.

Note: when a range is active, `last_brew` means "last brew within the selected range," not "the
absolute last brew ever." This is expected — don't add any special-casing to bypass the range for this
one field.

## 4. Backend changes: `src/brewops/api/main.py`

Add near the top of the file, with the other imports:

```python
from datetime import date, timedelta
from fastapi import Query
```

Add this function (don't reuse `parse_timestamp` — that one is for full datetimes on POST bodies and
rejects future dates, which is wrong here: a user should be able to pick a range like "this week" even
if today isn't over yet):

```python
def parse_date_range(start: str | None, end: str | None) -> tuple[str | None, str | None]:
    start_bound = None
    if start is not None:
        try:
            start_bound = date.fromisoformat(start).strftime("%Y-%m-%d 00:00:00")
        except ValueError:
            raise HTTPException(400, f"unparsable start date {start!r}")
    end_bound = None
    if end is not None:
        try:
            end_bound = (date.fromisoformat(end) + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
        except ValueError:
            raise HTTPException(400, f"unparsable end date {end!r}")
    if start_bound and end_bound and start_bound >= end_bound:
        raise HTTPException(400, "start date must be before end date")
    return start_bound, end_bound
```

Change the two existing routes:

```python
@app.get("/api/stats")
def stats(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
):
    start_bound, end_bound = parse_date_range(start, end)
    return queries.get_stats(conn, start_bound, end_bound)


@app.get("/api/machines/{machine_id}")
def machine_health(
    machine_id: int,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
):
    start_bound, end_bound = parse_date_range(start, end)
    health = queries.get_machine_health(conn, machine_id, start_bound, end_bound)
    if health is None:
        raise HTTPException(404, f"no machine with id {machine_id}")
    return health
```

Do **not** change `GET /api/machines` (plain machine list, no time-scoped data) or
`GET /api/drink-types` (static reference data).

## 5. Frontend changes

### `src/brewops/frontend/index.html`

Inside `<section id="dashboard">`, near the top (before the stat tiles), add a small filter bar:

```html
<div class="dashboard-filter">
  <label>From <input type="date" id="dash-start"></label>
  <label>To <input type="date" id="dash-end"></label>
  <button type="button" id="dash-clear">Clear</button>
</div>
```

Reuse existing input/button styling already used by the brew-log and maintenance forms in this file —
don't invent new CSS classes unless the existing ones look wrong once you view the page.

### `src/brewops/frontend/app.js`

Exact functions and what changes in each (line numbers refer to the file as it exists today, before
this change):

- **`loadDashboard()`** (lines 106–118) — the only *existing* function whose body changes:
  - Append the range query string to the `fetchJSON("/api/stats")` call (line 107) and to each
    `fetchJSON(\`/api/machines/${m.id}\`)` call (line 116). Do **not** append it to the
    `fetchJSON("/api/machines")` list call (line 114) — that endpoint has no time-scoped data.
  - Lines 109–110 currently do:
    ```js
    const lastDay = stats.per_day[stats.per_day.length - 1];
    document.getElementById("brews-today").textContent = lastDay ? lastDay.count : 0;
    ```
    This tile is labeled "Today" in `index.html` but actually just shows the count for whatever the
    *last* day in `stats.per_day` happens to be. That's fine when the range is unbounded (the last day
    really is today), but once a range can end in the past, this tile would silently become "brews on
    the last day of the range" while still saying "Today" — misleading (decision #3). Fix: when a
    range filter is active (i.e. `#dash-end` has a value, or more simply: whenever `rangeQS()` is
    non-empty), also update the tile's **label** element (not just its value) to something like
    "Last day in range"; when no range is active, restore the label to "Today". Find the label element
    in `index.html` next to `#brews-today` and give it an `id` (e.g. `#brews-today-label`) if it
    doesn't already have one addressable by JS.
- **New function `rangeQS()`**:
  ```js
  function rangeQS() {
    const start = document.getElementById("dash-start").value;
    const end = document.getElementById("dash-end").value;
    const params = new URLSearchParams();
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  }
  ```
  Called from `loadDashboard()`.
- **New function `initRangeFromURL()`**: run once, before the first `loadDashboard()` call (near line
  185), reads `new URLSearchParams(location.search)` and sets `#dash-start`/`#dash-end` values from
  it, so a bookmarked/shared URL restores the filter on load.
- **New function `onRangeChange()`**: attached as a `change` listener on both `#dash-start` and
  `#dash-end`, and a `click` listener on `#dash-clear` (which should also clear both inputs' values
  before proceeding). It should:
  - Update the URL via `history.replaceState(null, "", ...)` — use `replaceState`, not `pushState`,
    so every date tweak doesn't add a new browser-history entry.
  - Call `loadDashboard()` again.
- **No changes** to `renderTimeline`, `renderDrinkBars`, `renderUsageHistogram`, `renderMachineCards`,
  `fetchJSON`, `fillSelect`, `localNow`, `submitForm`, or `setupForms` — they render or consume
  whatever data/shape they're already given, and the API response shape is unchanged (same keys, just
  filtered values).

**Per-day chart with zero brews in the selected range**: `renderTimeline(perDay)` (lines 29–50)
already handles an empty series correctly — line 32, `if (perDay.length === 0) return;`, leaves
`<svg id="timeline">` empty (no bars, no error) when `stats.per_day` is `[]`. No code change is
needed here. Note this renders as a bare empty box with no "no data in this range" message — that's
acceptable for this ticket; don't add an explicit empty-state message unless asked.

## 6. Docs to update

- `docs/reference/api.md`: under `GET /api/stats` and `GET /api/machines/{machine_id}`, document the
  new `start` / `end` query params — format `YYYY-MM-DD`, both optional, inclusive range, `400` on
  malformed dates or `start` after `end`.
- `docs/conventions.md`: add a short note next to the existing "health-aggregate pattern" section that
  new per-machine stats should also accept and apply `start`/`end`, using `_range_clause` for
  consistency.

## 7. Edge cases to explicitly test

Write these as test cases (find the existing test files for `queries.py` and `main.py` under `tests/`
and follow their fixture/setup pattern):

1. **No range at all** (`start=None, end=None`) — `get_stats` and `get_machine_health` return exactly
   what they did before this change. This is the regression check that guarantees the default
   all-time view still works.
2. **Empty range** — a `start`/`end` pair that excludes every row (e.g. a date range far in the past
   before any seeded data). `get_stats` should return `total_brews: 0`, `per_day: []`, and `per_drink`
   with every drink type present at `count: 0` (not missing). `get_machine_health` should return
   `brew_count: 0`, `last_brew: None`, `specialty: None`, `last_maintenance: None`,
   `recent_errors: []`, and `usage_by_weekday` fully zero-filled.
3. **`start` after `end`** — call `GET /api/stats?start=2026-09-20&end=2026-09-01` and confirm a `400`
   response. Also test this directly against `parse_date_range` if there's a unit test file for
   `main.py` helpers.
4. **Malformed date** — `GET /api/stats?start=not-a-date` → `400`.
5. **One-sided range** — only `start` set (open-ended future) and only `end` set (open-ended past)
   both work and return partial totals, not errors.
6. **Boundary inclusivity** — seed a brew at exactly `<end> 23:59:59` and confirm it's included when
   that date is passed as `end`; seed a brew at `<end + 1 day> 00:00:00` and confirm it's **excluded**.
   This is the off-by-one case the half-open range in section 2 is designed to avoid.
7. **Zero-count drink type preserved** — seed at least one drink type with zero brews inside the test
   range, and confirm it still appears in `per_drink` with `count: 0` rather than being dropped. This
   directly verifies the `LEFT JOIN ... ON` placement from section 3.
8. **Days with no brews** — within a multi-day range where some days have zero brews, confirm
   `per_day` simply omits those days (it already works this way today; just confirm the range filter
   doesn't change that behavior or produce spurious zero-rows).
9. **Backward compatibility of `/api/machines`** — confirm this endpoint still ignores `start`/`end`
   even if a caller passes them (it currently takes no params in its handler, so this should be
   automatic — just don't accidentally add params to it).

## 8. How to verify the finished implementation

1. Run the test suite: `uv run pytest` (see docs/testing.md for details). All existing tests must
   still pass; all new tests from section 7 must pass.
2. Start the app: `uv run start`, open http://localhost:8123.
3. Manually confirm, on the running dashboard:
   - With no range picked, the numbers match what you see before this change (bragging-rights totals
     unchanged).
   - Picking a "From" and "To" date updates the stat tiles, the per-drink bars, the timeline chart,
     and every machine card together, not just some of them.
   - Picking a range with no data in it shows zeros/empty charts, not an error or a blank page.
   - Picking `From` after `To` shows a clear error state in the UI rather than a silent failure or a
     stack trace in the browser console.
   - Clicking "Clear" restores the all-time view.
   - Reloading the page after picking a range (with the URL now containing `?start=...&end=...`)
     keeps the same filter applied — confirms the URL round-trip works.
