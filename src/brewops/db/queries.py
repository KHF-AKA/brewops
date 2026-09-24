"""Read and write queries. All timestamps are naive local time strings."""

import sqlite3
from typing import Any


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


def get_machines(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, name, floor, has_telemetry FROM machines ORDER BY id")
    return [dict(r) | {"has_telemetry": bool(r["has_telemetry"])} for r in rows]


def get_machine(conn: sqlite3.Connection, machine_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, name, floor, has_telemetry FROM machines WHERE id = ?", (machine_id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row) | {"has_telemetry": bool(row["has_telemetry"])}


def get_drink_types(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT id, name, label FROM drink_types ORDER BY id")
    return [dict(r) for r in rows]


def drink_type_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM drink_types WHERE name = ?", (name,)).fetchone()
    return row is not None


def insert_brew(
    conn: sqlite3.Connection,
    machine_id: int,
    drink_type: str,
    timestamp: str,
    duration_s: float,
    temp_c: float,
    source: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO brew_events (machine_id, drink_type, timestamp, duration_s, temp_c, source)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (machine_id, drink_type, timestamp, duration_s, temp_c, source),
    )
    return cur.lastrowid


def insert_maintenance(
    conn: sqlite3.Connection,
    machine_id: int,
    type: str,
    timestamp: str,
    note: str | None = None,
    error_code: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO maintenance_events (machine_id, type, timestamp, note, error_code)
        VALUES (?, ?, ?, ?, ?)
        """,
        (machine_id, type, timestamp, note, error_code),
    )
    return cur.lastrowid


def get_stats(conn: sqlite3.Connection, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """Dashboard numbers: totals, per-drink, per-day."""
    total_clause, total_params = _range_clause("timestamp", start, end)
    total_where = f"WHERE {total_clause}" if total_clause else ""
    total = conn.execute(f"SELECT COUNT(*) AS n FROM brew_events {total_where}", total_params).fetchone()["n"]

    per_drink_clause, per_drink_params = _range_clause("be.timestamp", start, end)
    per_drink_join = f"AND {per_drink_clause}" if per_drink_clause else ""
    per_drink = [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT dt.name, dt.label, COUNT(be.id) AS count
            FROM drink_types dt
            LEFT JOIN brew_events be ON be.drink_type = dt.name {per_drink_join}
            GROUP BY dt.id
            ORDER BY dt.id
            """,
            per_drink_params
        )
    ]

    per_day_clause, per_day_params = _range_clause("timestamp", start, end)
    per_day_where = f"WHERE {per_day_clause}" if per_day_clause else ""
    per_day = [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT DATE(timestamp) AS day, COUNT(*) AS count
            FROM brew_events
            {per_day_where}
            GROUP BY DATE(timestamp)
            ORDER BY day
            """,
            per_day_params
        )
    ]
    return {"total_brews": total, "per_drink": per_drink, "per_day": per_day}


WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# SQLite strftime('%w', ...) is 0=Sunday..6=Saturday; reorder to Monday-first.
_WEEKDAY_SQLITE_ORDER = [1, 2, 3, 4, 5, 6, 0]


def get_machine_usage_by_weekday(conn: sqlite3.Connection, machine_id: int, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    """Brew counts by day of week (Monday-first), zero-filled, for the load histogram."""
    range_clause, range_params = _range_clause("timestamp", start, end)
    range_where = f"AND {range_clause}" if range_clause else ""
    rows = conn.execute(
        f"""
        SELECT CAST(strftime('%w', timestamp) AS INTEGER) AS dow, COUNT(*) AS count
        FROM brew_events
        WHERE machine_id = ? {range_where}
        GROUP BY dow
        """,
        (machine_id,) + tuple(range_params),
    )
    counts = {r["dow"]: r["count"] for r in rows}
    return [
        {"weekday": WEEKDAY_LABELS[i], "count": counts.get(dow, 0)}
        for i, dow in enumerate(_WEEKDAY_SQLITE_ORDER)
    ]


def get_machine_health(conn: sqlite3.Connection, machine_id: int, start: str | None = None, end: str | None = None) -> dict[str, Any] | None:
    """Machine card: brew activity plus maintenance history."""
    machine = get_machine(conn, machine_id)
    if machine is None:
        return None

    brews_clause, brews_params = _range_clause("timestamp", start, end)
    brews_where = f"AND {brews_clause}" if brews_clause else ""
    brews = conn.execute(
        f"""
        SELECT COUNT(*) AS count, MAX(timestamp) AS last_brew
        FROM brew_events WHERE machine_id = ? {brews_where}
        """,
        (machine_id,) + tuple(brews_params),
    ).fetchone()

    last_maint_clause, last_maint_params = _range_clause("timestamp", start, end)
    last_maint_where = f"AND {last_maint_clause}" if last_maint_clause else ""
    last_maintenance = conn.execute(
        f"""
        SELECT type, timestamp, note, error_code
        FROM maintenance_events
        WHERE machine_id = ? AND type != 'error' {last_maint_where}
        ORDER BY timestamp DESC LIMIT 1
        """,
        (machine_id,) + tuple(last_maint_params),
    ).fetchone()

    recent_errors_clause, recent_errors_params = _range_clause("timestamp", start, end)
    recent_errors_where = f"AND {recent_errors_clause}" if recent_errors_clause else ""
    recent_errors = [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT timestamp, error_code, note
            FROM maintenance_events
            WHERE machine_id = ? AND type = 'error' {recent_errors_where}
            ORDER BY timestamp DESC LIMIT 5
            """,
            (machine_id,) + tuple(recent_errors_params),
        )
    ]

    specialty_clause, specialty_params = _range_clause("be.timestamp", start, end)
    specialty_where = f"AND {specialty_clause}" if specialty_clause else ""
    specialty = conn.execute(
        f"""
        SELECT dt.name, dt.label, COUNT(*) AS count, MAX(be.timestamp) AS last_brewed
        FROM brew_events be
        JOIN drink_types dt ON dt.name = be.drink_type
        WHERE be.machine_id = ? {specialty_where}
        GROUP BY dt.id
        ORDER BY count DESC, last_brewed DESC
        LIMIT 1
        """,
        (machine_id,) + tuple(specialty_params),
    ).fetchone()

    return machine | {
        "brew_count": brews["count"],
        "last_brew": brews["last_brew"],
        "last_maintenance": dict(last_maintenance) if last_maintenance else None,
        "recent_errors": recent_errors,
        "specialty": dict(specialty) if specialty else None,
        "usage_by_weekday": get_machine_usage_by_weekday(conn, machine_id, start, end),
    }
