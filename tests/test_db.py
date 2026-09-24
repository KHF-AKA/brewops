import pytest

from brewops.db.connection import connect
from brewops.db.queries import (
    get_drink_types,
    get_machine_health,
    get_machine_usage_by_weekday,
    get_machines,
    get_stats,
    insert_brew,
    insert_maintenance,
)
from brewops.db.schema import init_db, reset_db


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


def test_init_is_idempotent(conn):
    """Calling init_db twice must not duplicate seeded machines/drink types."""
    init_db(conn)
    init_db(conn)
    assert len(get_machines(conn)) == 4
    assert len(get_drink_types(conn)) == 6


def test_reference_data_seeded(conn):
    """The fixed fleet and drink menu are present after init, with correct fields."""
    machines = {m["name"]: m for m in get_machines(conn)}
    assert "Bertha (3rd floor)" in machines
    assert machines["Old Faithful (2nd floor)"]["has_telemetry"] is False
    drinks = {d["name"] for d in get_drink_types(conn)}
    assert "espresso" in drinks


def test_stats_math(conn):
    """get_stats totals, per-drink counts, and per-day counts all match inserted brews."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.5, 92.0, "csv")
    insert_brew(conn, 1, "espresso", "2026-06-01 09:00:00", 26.0, 91.5, "csv")
    insert_brew(conn, 2, "latte", "2026-06-02 10:00:00", 44.0, 88.0, "csv")
    insert_brew(conn, 3, "lungo", "2026-06-02 11:00:00", 38.0, 90.0, "manual")
    conn.commit()

    stats = get_stats(conn)
    assert stats["total_brews"] == 4
    per_drink = {d["name"]: d["count"] for d in stats["per_drink"]}
    assert per_drink["espresso"] == 2
    assert per_drink["latte"] == 1
    assert per_drink["cappuccino"] == 0
    per_day = {d["day"]: d["count"] for d in stats["per_day"]}
    assert per_day == {"2026-06-01": 2, "2026-06-02": 2}


def test_machine_health(conn):
    """get_machine_health bundles brew count, last brew, last maintenance,
    recent errors, and specialty into one dict for a single machine."""
    insert_brew(conn, 4, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_maintenance(conn, 4, "descale", "2026-06-03 18:00:00", note="quarterly descale")
    insert_maintenance(conn, 4, "error", "2026-06-04 09:15:00", error_code="E42")
    conn.commit()

    health = get_machine_health(conn, 4)
    assert health["brew_count"] == 1
    assert health["last_brew"] == "2026-06-01 08:00:00"
    assert health["last_maintenance"]["type"] == "descale"
    assert health["recent_errors"][0]["error_code"] == "E42"
    assert health["specialty"] == {
        "name": "espresso",
        "label": "Espresso",
        "count": 1,
        "last_brewed": "2026-06-01 08:00:00",
    }
    assert health["usage_by_weekday"] == [
        {"weekday": "Mon", "count": 1},
        {"weekday": "Tue", "count": 0},
        {"weekday": "Wed", "count": 0},
        {"weekday": "Thu", "count": 0},
        {"weekday": "Fri", "count": 0},
        {"weekday": "Sat", "count": 0},
        {"weekday": "Sun", "count": 0},
    ]


def test_machine_health_unknown_machine(conn):
    """get_machine_health returns None for a machine id that doesn't exist."""
    assert get_machine_health(conn, 999) is None


def test_machine_health_specialty_none_without_brews(conn):
    """specialty is None when the machine has no brew_events rows yet."""
    health = get_machine_health(conn, 3)
    assert health["specialty"] is None


def test_machine_health_specialty_picks_highest_count(conn):
    """specialty is the drink type with the most brews for that machine."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 1, "espresso", "2026-06-01 09:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 1, "latte", "2026-06-01 10:00:00", 40.0, 88.0, "csv")
    conn.commit()

    health = get_machine_health(conn, 1)
    assert health["specialty"]["name"] == "espresso"
    assert health["specialty"]["count"] == 2


def test_machine_health_specialty_tiebreak_by_most_recent(conn):
    """When two drinks tie on count, specialty picks whichever was brewed most recently."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 1, "latte", "2026-06-02 08:00:00", 40.0, 88.0, "csv")
    conn.commit()

    health = get_machine_health(conn, 1)
    assert health["specialty"]["name"] == "latte"
    assert health["specialty"]["last_brewed"] == "2026-06-02 08:00:00"


def test_machine_usage_by_weekday_zero_filled(conn):
    """A machine with no brews gets all seven weekdays back with count 0, Monday-first."""
    usage = get_machine_usage_by_weekday(conn, 2)
    assert [u["weekday"] for u in usage] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert all(u["count"] == 0 for u in usage)


def test_machine_usage_by_weekday_counts(conn):
    """Brews are bucketed onto the correct day of week regardless of insertion order."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")  # Monday
    insert_brew(conn, 1, "espresso", "2026-06-01 18:00:00", 27.0, 92.0, "csv")  # Monday
    insert_brew(conn, 1, "latte", "2026-06-03 09:00:00", 40.0, 88.0, "csv")  # Wednesday
    insert_brew(conn, 1, "lungo", "2026-06-07 09:00:00", 38.0, 90.0, "csv")  # Sunday
    conn.commit()

    usage = {u["weekday"]: u["count"] for u in get_machine_usage_by_weekday(conn, 1)}
    assert usage == {"Mon": 2, "Tue": 0, "Wed": 1, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 1}


def test_reset_db_clears_events(conn):
    """reset_db drops all brew/maintenance data but reseeds the machine/drink reference data."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    conn.commit()
    reset_db(conn)
    assert get_stats(conn)["total_brews"] == 0
    assert len(get_machines(conn)) == 4


def test_get_stats_no_range_returns_all_time(conn):
    """With no range parameters, get_stats returns the same as before (all-time view)."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 1, "espresso", "2026-06-15 09:00:00", 26.0, 91.5, "csv")
    insert_brew(conn, 2, "latte", "2026-07-02 10:00:00", 44.0, 88.0, "csv")
    conn.commit()

    stats = get_stats(conn)
    assert stats["total_brews"] == 3
    assert {d["name"]: d["count"] for d in stats["per_drink"]}["espresso"] == 2


def test_get_stats_with_range(conn):
    """get_stats filters by date range: inclusive on both ends."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 1, "espresso", "2026-06-15 09:00:00", 26.0, 91.5, "csv")
    insert_brew(conn, 2, "latte", "2026-07-02 10:00:00", 44.0, 88.0, "csv")
    conn.commit()

    stats = get_stats(conn, "2026-06-01 00:00:00", "2026-06-30 00:00:00")
    assert stats["total_brews"] == 2
    assert {d["day"]: d["count"] for d in stats["per_day"]} == {"2026-06-01": 1, "2026-06-15": 1}


def test_get_stats_one_sided_range(conn):
    """get_stats works with only start or only end."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 1, "espresso", "2026-06-15 09:00:00", 26.0, 91.5, "csv")
    insert_brew(conn, 2, "latte", "2026-07-02 10:00:00", 44.0, 88.0, "csv")
    conn.commit()

    only_start = get_stats(conn, "2026-06-15 00:00:00", None)
    assert only_start["total_brews"] == 2

    only_end = get_stats(conn, None, "2026-06-30 00:00:00")
    assert only_end["total_brews"] == 2


def test_get_stats_empty_range(conn):
    """get_stats with an empty range returns zero totals and zero-filled per_drink."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 2, "latte", "2026-06-02 10:00:00", 44.0, 88.0, "csv")
    conn.commit()

    stats = get_stats(conn, "2026-05-01 00:00:00", "2026-05-30 00:00:00")
    assert stats["total_brews"] == 0
    assert stats["per_day"] == []
    per_drink = {d["name"]: d["count"] for d in stats["per_drink"]}
    assert per_drink["espresso"] == 0
    assert per_drink["latte"] == 0
    assert per_drink["cappuccino"] == 0


def test_get_stats_preserves_zero_count_drinks_in_range(conn):
    """per_drink includes drinks with zero brews in the range (LEFT JOIN behavior)."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 2, "latte", "2026-06-02 10:00:00", 44.0, 88.0, "csv")
    conn.commit()

    stats = get_stats(conn, "2026-06-01 00:00:00", "2026-06-02 00:00:00")
    per_drink = {d["name"]: d["count"] for d in stats["per_drink"]}
    assert per_drink["espresso"] == 1
    assert per_drink["latte"] == 0
    assert per_drink["cappuccino"] == 0


def test_get_machine_health_with_range(conn):
    """get_machine_health filters all stats by date range."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_brew(conn, 1, "espresso", "2026-07-15 09:00:00", 26.0, 91.5, "csv")
    insert_maintenance(conn, 1, "descale", "2026-06-03 18:00:00")
    insert_maintenance(conn, 1, "error", "2026-07-04 09:15:00", error_code="E42")
    conn.commit()

    health = get_machine_health(conn, 1, "2026-06-01 00:00:00", "2026-06-30 00:00:00")
    assert health["brew_count"] == 1
    assert health["last_brew"] == "2026-06-01 08:00:00"
    assert health["last_maintenance"]["type"] == "descale"
    assert len(health["recent_errors"]) == 0
    assert health["specialty"]["name"] == "espresso"


def test_get_machine_health_empty_range(conn):
    """get_machine_health in an empty range returns zero counts and None values."""
    insert_brew(conn, 1, "espresso", "2026-06-01 08:00:00", 27.0, 92.0, "csv")
    insert_maintenance(conn, 1, "descale", "2026-06-03 18:00:00")
    conn.commit()

    health = get_machine_health(conn, 1, "2026-05-01 00:00:00", "2026-05-30 00:00:00")
    assert health["brew_count"] == 0
    assert health["last_brew"] is None
    assert health["last_maintenance"] is None
    assert health["recent_errors"] == []
    assert health["specialty"] is None
    assert all(u["count"] == 0 for u in health["usage_by_weekday"])
