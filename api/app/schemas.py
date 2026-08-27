from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class TimeEntryCreate(BaseModel):
    spent_on: date
    started_at: time | None = None
    ended_at: time | None = None
    duration_hours: Decimal
    category_code: str | None = None
    description: str
    ticket_external_id: str | None = None
    project_name: str | None = None
    transport_name: str | None = None
    km: Decimal | None = None
    redmine_time: str | None = None
    reported_status: str | None = None
    raw_text: str | None = None


class TimeEntryOut(BaseModel):
    id: UUID
    spent_on: date
    started_at: time | None
    ended_at: time | None
    duration_hours: Decimal
    overlap_hours: Decimal | None
    effective_hours: Decimal
    category_code: str | None
    description: str
    ticket_external_id: str | None
    project_name: str | None
    transport_name: str | None
    km: Decimal | None
    reported_status: str | None


class TextEntryParseRequest(BaseModel):
    text: str
    spent_on: date | None = None
    category_code: str | None = None


class TextEntryParseResponse(BaseModel):
    original_text: str
    draft: dict
    matched_ticket: dict | None
    confidence_notes: list[str]


class OverheadTicketOut(BaseModel):
    external_id: str
    project_name: str | None
    subject: str | None
    source_period: str | None
    valid_from: datetime | None
    valid_to: datetime | None


class OverheadTicketValidityUpdate(BaseModel):
    external_ids: list[str]
    valid_from: date | None = None
    valid_to: date | None = None


class BulkUpdateResponse(BaseModel):
    updated_count: int


class SummaryRow(BaseModel):
    year: int
    month: int
    hours: Decimal


class ProjectSummaryRow(BaseModel):
    project_name: str
    hours: Decimal


class PeriodSummaryRow(BaseModel):
    period_key: str
    period_label: str
    date_from: date
    date_to: date
    hours: Decimal


class CategoryPeriodRow(BaseModel):
    period_key: str
    period_label: str
    date_from: date
    date_to: date
    abra_hours: Decimal
    education_hours: Decimal
    private_hours: Decimal
    movement_hours: Decimal
    tanaka_hours: Decimal
    total_hours: Decimal


class CategoryComparisonRow(BaseModel):
    category_key: str
    label: str
    current_week_hours: Decimal
    previous_week_hours: Decimal
    week_delta_hours: Decimal
    current_month_hours: Decimal
    previous_month_same_period_hours: Decimal
    month_delta_hours: Decimal


class CategoryComparisonOut(BaseModel):
    today: date
    current_week_from: date
    current_week_to: date
    previous_week_from: date
    previous_week_to: date
    current_month_from: date
    current_month_to: date
    previous_month_from: date
    previous_month_to: date
    rows: list[CategoryComparisonRow]


class VoiceParseRequest(BaseModel):
    text: str


class VoiceParseResponse(BaseModel):
    original_text: str
    draft: dict
    confidence_notes: list[str]


class FuelVehicleOut(BaseModel):
    id: UUID
    code: str
    name: str
    is_active: bool
    sort_order: int


class FuelEntryBase(BaseModel):
    vehicle_id: UUID
    purchased_on: date
    purchased_at: time | None = None
    station: str | None = None
    fuel_type: str | None = None
    odometer_km: Decimal | None = None
    liters: Decimal | None = None
    total_price_vat: Decimal | None = None
    total_price_no_vat: Decimal | None = None
    price_per_liter: Decimal | None = None
    trip_km: Decimal | None = None
    full_tank: bool | None = None
    average_consumption: Decimal | None = None
    note: str | None = None


class FuelEntryCreate(FuelEntryBase):
    pass


class FuelEntryUpdate(BaseModel):
    vehicle_id: UUID | None = None
    purchased_on: date | None = None
    purchased_at: time | None = None
    station: str | None = None
    fuel_type: str | None = None
    odometer_km: Decimal | None = None
    liters: Decimal | None = None
    total_price_vat: Decimal | None = None
    total_price_no_vat: Decimal | None = None
    price_per_liter: Decimal | None = None
    trip_km: Decimal | None = None
    full_tank: bool | None = None
    average_consumption: Decimal | None = None
    note: str | None = None


class FuelEntryOut(FuelEntryBase):
    id: UUID
    vehicle_name: str
    receipt_photo_path: str | None
    dashboard_photo_path: str | None
    source: str
    source_sheet: str | None
    source_row: int | None


class FuelSummaryRow(BaseModel):
    period_key: str
    period_label: str
    level: str
    liters: Decimal
    total_price_vat: Decimal
    trip_km: Decimal
    average_consumption: Decimal | None


class FuelImportResponse(BaseModel):
    imported_rows: int
    skipped_rows: int


class FuelPhotoParseResponse(BaseModel):
    draft: dict
    confidence_notes: list[str]
    raw_text: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserOut(BaseModel):
    username: str
    role: str


class UserOut(BaseModel):
    username: str
    role: str
    is_active: bool


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    is_active: bool = True


class UserUpdate(BaseModel):
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None
