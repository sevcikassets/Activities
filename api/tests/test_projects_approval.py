from datetime import date, datetime

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")

from sqlalchemy import text

from app.auth import bootstrap_admin_user, ensure_user_schema
from app.db import SessionLocal
from app.repository import (
    approve_time_entry,
    bulk_approve_time_entries,
    create_project,
    create_time_entry,
    ensure_fuel_schema,
    ensure_project_schema,
    list_time_entries,
    update_project,
    update_time_entry,
)
from app.schemas import TimeEntryCreate


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_schema():
    import psycopg

    from app.config import settings

    try:
        # A short, explicit timeout here (independent of the app's pooled
        # SQLAlchemy engine, which has none) so an unreachable database skips
        # fast instead of hanging on the OS-level connect timeout.
        probe = psycopg.connect(settings.database_url.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=2)
        probe.close()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable ({exc}); skipping project/approval tests.")
    session = SessionLocal()
    ensure_fuel_schema(session)
    ensure_project_schema(session)
    ensure_user_schema(session)
    bootstrap_admin_user(session)
    session.close()


@pytest.fixture()
def db():
    session = SessionLocal()
    session.execute(text("DELETE FROM time_entries"))
    session.execute(text("DELETE FROM projects"))
    session.commit()
    yield session
    session.close()


def _entry(project_name: str, description: str = "work", spent_on: date = date(2026, 1, 1)) -> TimeEntryCreate:
    return TimeEntryCreate(spent_on=spent_on, duration_hours=1, description=description, project_name=project_name)


def test_standard_project_auto_approves(db):
    create_project(db, "Standard", project_type="standard")
    entry = create_time_entry(db, _entry("Standard"))
    assert entry.approved_at is not None


def test_overhead_project_auto_approves(db):
    create_project(db, "Overhead", project_type="overhead")
    entry = create_time_entry(db, _entry("Overhead"))
    assert entry.approved_at is not None


def test_approval_project_stays_unapproved(db):
    create_project(db, "NeedsApproval", project_type="approval", approval_due_date=date(2026, 12, 31))
    entry = create_time_entry(db, _entry("NeedsApproval"))
    assert entry.approved_at is None


def test_entry_without_project_auto_approves(db):
    entry = create_time_entry(db, _entry(None))
    assert entry.approved_at is not None


def test_approve_time_entry_sets_timestamp(db):
    create_project(db, "NeedsApproval", project_type="approval")
    entry = create_time_entry(db, _entry("NeedsApproval"))
    approved = approve_time_entry(db, entry.id)
    assert approved.approved_at is not None


def test_bulk_approve_time_entries(db):
    create_project(db, "NeedsApproval", project_type="approval")
    entry = create_time_entry(db, _entry("NeedsApproval"))
    count = bulk_approve_time_entries(db, [entry.id])
    assert count == 1


def test_only_unapproved_filter_returns_pending_entries_only(db):
    create_project(db, "Standard", project_type="standard")
    create_project(db, "NeedsApproval", project_type="approval")
    create_time_entry(db, _entry("Standard", "approved one"))
    pending = create_time_entry(db, _entry("NeedsApproval", "pending one"))
    results = list_time_entries(db, only_unapproved=True)
    assert [row.id for row in results] == [pending.id]


def test_editing_an_entry_does_not_revoke_existing_approval(db):
    create_project(db, "NeedsApproval", project_type="approval")
    entry = create_time_entry(db, _entry("NeedsApproval"))
    approve_time_entry(db, entry.id)
    updated = update_time_entry(db, entry.id, _entry("NeedsApproval", "edited description"))
    assert updated.approved_at is not None


def test_default_category_code_fills_in_from_project(db):
    create_project(db, "Overhead", project_type="overhead", default_category_code="A")
    entry = create_time_entry(db, _entry("Overhead"))
    assert entry.category_code == "A"


def test_explicit_category_code_overrides_project_default(db):
    create_project(db, "Overhead", project_type="overhead", default_category_code="A")
    payload = _entry("Overhead")
    payload.category_code = "S"
    entry = create_time_entry(db, payload)
    assert entry.category_code == "S"


def test_create_project_rejects_invalid_type(db):
    with pytest.raises(ValueError):
        create_project(db, "Bad", project_type="bogus")


def test_create_project_rejects_duplicate_name(db):
    create_project(db, "Dup", project_type="standard")
    with pytest.raises(ValueError):
        create_project(db, "Dup", project_type="standard")


def test_switching_project_away_from_approval_clears_due_date(db):
    project = create_project(db, "Temp", project_type="approval", approval_due_date=date(2026, 6, 30))
    updated = update_project(db, project.id, project_type="standard")
    assert updated.approval_due_date is None


def test_migration_backfills_legacy_rows_for_non_approval_projects(db):
    project = create_project(db, "Legacy", project_type="standard")
    db.execute(
        text(
            "INSERT INTO time_entries (spent_on, duration_hours, description, project_id, created_at) "
            "VALUES (:spent_on, 1, 'legacy row', :project_id, :created_at)"
        ),
        {"spent_on": date(2020, 1, 1), "project_id": project.id, "created_at": datetime(2020, 1, 1)},
    )
    db.commit()
    ensure_project_schema(db)
    approved_at = db.execute(text("SELECT approved_at FROM time_entries WHERE description = 'legacy row'")).scalar()
    assert approved_at is not None


def test_migration_leaves_legacy_rows_on_approval_projects_untouched(db):
    project = create_project(db, "LegacyApproval", project_type="approval")
    db.execute(
        text(
            "INSERT INTO time_entries (spent_on, duration_hours, description, project_id, created_at) "
            "VALUES (:spent_on, 1, 'legacy pending row', :project_id, :created_at)"
        ),
        {"spent_on": date(2020, 1, 1), "project_id": project.id, "created_at": datetime(2020, 1, 1)},
    )
    db.commit()
    ensure_project_schema(db)
    approved_at = db.execute(text("SELECT approved_at FROM time_entries WHERE description = 'legacy pending row'")).scalar()
    assert approved_at is None
