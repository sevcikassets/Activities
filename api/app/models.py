from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, Text, Time, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Category(Base):
    __tablename__ = "categories"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True)
    normalized_name: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Transport(Base):
    __tablename__ = "transports"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[str] = mapped_column(Text, unique=True)
    project_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("projects.id"))
    subject: Mapped[str | None] = mapped_column(Text)
    is_overhead: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_period: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project | None] = relationship()


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    spent_on: Mapped[date] = mapped_column(Date)
    started_at: Mapped[time | None] = mapped_column(Time)
    ended_at: Mapped[time | None] = mapped_column(Time)
    duration_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    category_code: Mapped[str | None] = mapped_column(Text, ForeignKey("categories.code"))
    description: Mapped[str] = mapped_column(Text)
    ticket_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("tickets.id"))
    project_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("projects.id"))
    transport_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("transports.id"))
    km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    overlap_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), default=0)
    redmine_time: Mapped[str | None] = mapped_column(Text)
    reported_status: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="manual")
    source_row: Mapped[int | None]
    raw_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project | None] = relationship()
    ticket: Mapped[Ticket | None] = relationship()
    category: Mapped[Category | None] = relationship()
    transport: Mapped[Transport | None] = relationship()


class VoiceInput(Base):
    __tablename__ = "voice_inputs"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    original_text: Mapped[str] = mapped_column(Text)
    parsed_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text, default="draft")
    created_entry_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("time_entries.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FuelVehicle(Base):
    __tablename__ = "fuel_vehicles"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(default=0)
    source_sheets: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fuel_entries: Mapped[list["FuelEntry"]] = relationship(back_populates="vehicle")


class FuelEntry(Base):
    __tablename__ = "fuel_entries"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    vehicle_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("fuel_vehicles.id"))
    purchased_on: Mapped[date] = mapped_column(Date)
    purchased_at: Mapped[time | None] = mapped_column(Time)
    station: Mapped[str | None] = mapped_column(Text)
    fuel_type: Mapped[str | None] = mapped_column(Text)
    odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    liters: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    total_price_vat: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_price_no_vat: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_per_liter: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    trip_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    full_tank: Mapped[bool | None] = mapped_column(Boolean)
    average_consumption: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    note: Mapped[str | None] = mapped_column(Text)
    receipt_photo_path: Mapped[str | None] = mapped_column(Text)
    dashboard_photo_path: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="manual")
    source_sheet: Mapped[str | None] = mapped_column(Text)
    source_row: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vehicle: Mapped[FuelVehicle] = relationship(back_populates="fuel_entries")
