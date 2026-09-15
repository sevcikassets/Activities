from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")

from sqlalchemy import text

from app.db import SessionLocal
from app.repository import (
    create_fuel_entry,
    delete_fuel_entry,
    ensure_fuel_schema,
    list_fuel_entries,
    list_fuel_vehicles,
    seed_fuel_vehicles,
)
from app.schemas import FuelEntryCreate


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_schema():
    import psycopg

    from app.config import settings

    try:
        probe = psycopg.connect(settings.database_url.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=2)
        probe.close()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable ({exc}); skipping fuel entry tests.")
    session = SessionLocal()
    ensure_fuel_schema(session)
    seed_fuel_vehicles(session)
    session.close()


@pytest.fixture()
def db():
    session = SessionLocal()
    session.execute(text("DELETE FROM fuel_entries"))
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def vehicle_id(db):
    return list_fuel_vehicles(db)[0].id


def _fuel_entry(vehicle_id, purchased_on, odometer_km) -> FuelEntryCreate:
    return FuelEntryCreate(
        vehicle_id=vehicle_id,
        purchased_on=purchased_on,
        odometer_km=Decimal(str(odometer_km)),
        liters=Decimal("40"),
        total_price_vat=Decimal("1500"),
        full_tank=True,
    )


def test_delete_fuel_entry_removes_it(db, vehicle_id):
    entry = create_fuel_entry(db, _fuel_entry(vehicle_id, date(2026, 1, 1), 1000))
    assert delete_fuel_entry(db, entry.id) is True
    remaining = list_fuel_entries(db, vehicle_id=vehicle_id)
    assert entry.id not in [row.id for row in remaining]


def test_delete_missing_fuel_entry_returns_false(db):
    assert delete_fuel_entry(db, "00000000-0000-0000-0000-000000000000") is False


def test_delete_fuel_entry_recalculates_later_entries(db, vehicle_id):
    entry1 = create_fuel_entry(db, _fuel_entry(vehicle_id, date(2026, 1, 1), 1000))
    entry2 = create_fuel_entry(db, _fuel_entry(vehicle_id, date(2026, 2, 1), 1500))
    entry3 = create_fuel_entry(db, _fuel_entry(vehicle_id, date(2026, 3, 1), 2000))
    remaining = {row.id: row for row in list_fuel_entries(db, vehicle_id=vehicle_id)}
    assert remaining[entry3.id].trip_km == Decimal("500.00")

    delete_fuel_entry(db, entry2.id)

    remaining = {row.id: row for row in list_fuel_entries(db, vehicle_id=vehicle_id)}
    assert entry2.id not in remaining
    # entry3's previous odometer reading is now entry1's, not the deleted entry2's.
    assert remaining[entry3.id].trip_km == Decimal("1000.00")
