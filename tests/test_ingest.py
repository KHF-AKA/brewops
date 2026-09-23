from datetime import datetime

import pytest

from brewops.db.connection import connect
from brewops.db.schema import init_db
from brewops.ingest.loader import ingest_path

NOW = datetime(2026, 7, 1, 12, 0, 0)

BREW_HEADER = "machine_id,drink,timestamp,duration_s,temp_c\n"
MAINT_HEADER = "machine_id,type,timestamp,note,error_code\n"


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


def test_happy_path_brews(conn, tmp_path):
    """A well-formed brews_*.csv loads every row with source='csv'."""
    f = tmp_path / "brews_2026-06.csv"
    f.write_text(
        BREW_HEADER
        + "1,espresso,2026-06-01 08:00:00,27.5,92.0\n"
        + "2,latte,2026-06-01 09:30:00,44.0,88.5\n",
        encoding="utf-8",
    )
    report = ingest_path(conn, f, now=NOW)
    assert report.brews_loaded == 2
    assert report.rejected == []
    sources = {r["source"] for r in conn.execute("SELECT source FROM brew_events")}
    assert sources == {"csv"}


def test_manual_file_gets_manual_source(conn, tmp_path):
    """A manual_*.csv loads brews tagged source='manual', not 'csv'."""
    f = tmp_path / "manual_log_export.csv"
    f.write_text(BREW_HEADER + "3,lungo,2026-06-01 10:00:00,38.0,90.0\n", encoding="utf-8")
    report = ingest_path(conn, f, now=NOW)
    assert report.brews_loaded == 1
    row = conn.execute("SELECT source FROM brew_events").fetchone()
    assert row["source"] == "manual"


def test_malformed_rows_rejected_but_file_continues(conn, tmp_path):
    """Each kind of bad row (unknown machine/drink, bad/future timestamp, bad numeric)
    is rejected individually while the rest of the file still loads."""
    f = tmp_path / "brews_bad.csv"
    f.write_text(
        BREW_HEADER
        + "99,espresso,2026-06-01 08:00:00,27.5,92.0\n"   # unknown machine
        + "1,unicorn_frappe,2026-06-01 08:05:00,27.5,92.0\n"  # unknown drink
        + "1,espresso,junk,27.5,92.0\n"                    # bad timestamp
        + "1,espresso,2027-01-01 08:00:00,27.5,92.0\n"     # future timestamp
        + "1,espresso,2026-06-01 08:10:00,zero,92.0\n"     # bad numeric
        + "1,espresso,2026-06-01 08:15:00,27.5,92.0\n",    # good
        encoding="utf-8",
    )
    report = ingest_path(conn, f, now=NOW)
    assert report.brews_loaded == 1
    assert len(report.rejected) == 5
    reasons = " | ".join(r[2] for r in report.rejected)
    assert "unknown machine_id" in reasons
    assert "unknown drink" in reasons
    assert "unparsable timestamp" in reasons
    assert "future" in reasons


def test_maintenance_file(conn, tmp_path):
    """A maintenance_*.csv loads valid rows and rejects an unknown maintenance type."""
    f = tmp_path / "maintenance_2026-06.csv"
    f.write_text(
        MAINT_HEADER
        + "1,descale,2026-06-15 18:00:00,quarterly descale,\n"
        + "4,error,2026-06-16 09:00:00,,E42\n"
        + "4,exploded,2026-06-17 09:00:00,,\n",  # unknown type
        encoding="utf-8",
    )
    report = ingest_path(conn, f, now=NOW)
    assert report.maintenance_loaded == 2
    assert len(report.rejected) == 1
    assert "unknown maintenance type" in report.rejected[0][2]
    row = conn.execute(
        "SELECT error_code FROM maintenance_events WHERE type = 'error'"
    ).fetchone()
    assert row["error_code"] == "E42"


def test_unrecognized_filename_skipped(conn, tmp_path):
    """A CSV not matching the brews_/manual_/maintenance_ naming convention is skipped entirely."""
    f = tmp_path / "notes.csv"
    f.write_text("whatever\n1\n", encoding="utf-8")
    report = ingest_path(conn, f, now=NOW)
    assert report.skipped_files == ["notes.csv"]
    assert report.files == 0


def test_directory_ingest_is_sorted_and_complete(conn, tmp_path):
    """Ingesting a directory processes every recognized CSV in it, brews and maintenance alike."""
    (tmp_path / "brews_a.csv").write_text(
        BREW_HEADER + "1,espresso,2026-06-01 08:00:00,27.5,92.0\n", encoding="utf-8"
    )
    (tmp_path / "maintenance_a.csv").write_text(
        MAINT_HEADER + "1,refill,2026-06-02 08:00:00,beans,\n", encoding="utf-8"
    )
    report = ingest_path(conn, tmp_path, now=NOW)
    assert report.files == 2
    assert report.brews_loaded == 1
    assert report.maintenance_loaded == 1
