from pathlib import Path
from decimal import Decimal
from io import BytesIO
from tempfile import NamedTemporaryFile
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app import models
from app.auth import AuthUser, authenticate, bootstrap_admin_user, create_user, list_users, require_admin, require_editor, require_user, update_user
from app.config import settings
from app.db import SessionLocal, get_db
from app.excel_import import import_workbook
from app.fuel_ocr import FuelOcrUnavailable, parse_fuel_photos
from app.repository import (
    category_comparison,
    category_period_summary,
    create_fuel_entry,
    create_time_entry,
    delete_time_entry,
    ensure_fuel_schema,
    fuel_summary,
    get_fuel_vehicle,
    import_fuel_workbook,
    list_fuel_entries,
    list_fuel_vehicles,
    list_overhead_tickets,
    list_time_entries,
    monthly_summary,
    normalize_time_entry_descriptions,
    parse_text_entry,
    period_summary,
    project_summary,
    seed_fuel_vehicles,
    update_fuel_entry,
    update_time_entry,
    update_overhead_ticket_validity,
)
from app.schemas import (
    BulkUpdateResponse,
    CategoryComparisonOut,
    CategoryPeriodRow,
    CurrentUserOut,
    FuelEntryCreate,
    FuelEntryOut,
    FuelEntryUpdate,
    FuelImportResponse,
    FuelPhotoParseResponse,
    FuelSummaryRow,
    FuelVehicleOut,
    LoginRequest,
    LoginResponse,
    OverheadTicketOut,
    OverheadTicketValidityUpdate,
    PeriodSummaryRow,
    ProjectSummaryRow,
    SummaryRow,
    TextEntryParseRequest,
    TextEntryParseResponse,
    TimeEntryCreate,
    TimeEntryOut,
    UserCreate,
    UserOut,
    UserUpdate,
    VoiceParseRequest,
    VoiceParseResponse,
)
from app.voice import parse_voice_text


app = FastAPI(
    title="Activities API",
    docs_url="/docs" if settings.api_enable_docs else None,
    redoc_url="/redoc" if settings.api_enable_docs else None,
    openapi_url="/openapi.json" if settings.api_enable_docs else None,
)

if settings.allowed_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response


_failed_logins: dict[str, list[datetime]] = {}


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _login_locked_out(ip: str) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=settings.login_lockout_seconds)
    attempts = [stamp for stamp in _failed_logins.get(ip, []) if stamp > cutoff]
    _failed_logins[ip] = attempts
    return len(attempts) >= settings.login_max_attempts


def _record_failed_login(ip: str) -> None:
    _failed_logins.setdefault(ip, []).append(datetime.now(timezone.utc))


def _clear_failed_logins(ip: str) -> None:
    _failed_logins.pop(ip, None)


def _rate_limit_response() -> None:
    raise HTTPException(
        status_code=429,
        detail="Too many failed login attempts. Try again later.",
        headers={"Retry-After": str(settings.login_lockout_seconds)},
    )


@app.on_event("startup")
def startup() -> None:
    with SessionLocal() as db:
        ensure_fuel_schema(db)
        bootstrap_admin_user(db)
        seed_fuel_vehicles(db)
        normalize_time_entry_descriptions(db)


def display_transport_name(name: str | None) -> str | None:
    if not name:
        return None
    normalized = name.lower()
    if "volvo xc90" in normalized:
        return "Volvo XC90"
    if "vlak" in normalized:
        return "vlak"
    if "autobus" in normalized:
        return "autobus"
    if "metro" in normalized or "mhd" in normalized:
        return "MHD"
    return name


def serialize_entry(entry: models.TimeEntry) -> TimeEntryOut:
    overlap_hours = entry.overlap_hours or Decimal("0")
    return TimeEntryOut(
        id=entry.id,
        spent_on=entry.spent_on,
        started_at=entry.started_at,
        ended_at=entry.ended_at,
        duration_hours=entry.duration_hours,
        overlap_hours=entry.overlap_hours,
        effective_hours=entry.duration_hours - overlap_hours,
        category_code=entry.category_code,
        description=entry.description,
        ticket_external_id=entry.ticket.external_id if entry.ticket else None,
        project_name=entry.project.name if entry.project else None,
        transport_name=display_transport_name(entry.transport.name if entry.transport else None),
        km=entry.km,
        reported_status=entry.reported_status,
    )


def serialize_fuel_entry(entry: models.FuelEntry) -> FuelEntryOut:
    return FuelEntryOut(
        id=entry.id,
        vehicle_id=entry.vehicle_id,
        vehicle_name=entry.vehicle.name,
        purchased_on=entry.purchased_on,
        purchased_at=entry.purchased_at,
        station=entry.station,
        fuel_type=entry.fuel_type,
        odometer_km=entry.odometer_km,
        liters=entry.liters,
        total_price_vat=entry.total_price_vat,
        total_price_no_vat=entry.total_price_no_vat,
        price_per_liter=entry.price_per_liter,
        trip_km=entry.trip_km,
        full_tank=entry.full_tank,
        average_consumption=entry.average_consumption,
        note=entry.note,
        receipt_photo_path=entry.receipt_photo_path,
        dashboard_photo_path=entry.dashboard_photo_path,
        source=entry.source,
        source_sheet=entry.source_sheet,
        source_row=entry.source_row,
    )


def decimal_or_none(value: str | None) -> Decimal | None:
    if not value:
        return None
    return Decimal(value.replace(" ", "").replace(",", "."))


def bool_or_none(value: str | None) -> bool | None:
    if value in (None, ""):
        return None
    return value.lower() in {"true", "1", "ano", "yes"}


async def save_upload(file: UploadFile | None, prefix: str) -> str | None:
    if not file or not file.filename:
        return None
    upload_dir = Path("/app/uploads/fuel")
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(char if char.isalnum() or char in ".-_" else "_" for char in file.filename)
    target = upload_dir / f"{prefix}-{safe_name}"
    target.write_bytes(await file.read())
    return str(target)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    ip = _client_ip(request)
    if _login_locked_out(ip):
        _rate_limit_response()
    token = authenticate(db, payload.username, payload.password)
    if not token:
        _record_failed_login(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    _clear_failed_logins(ip)
    return LoginResponse(access_token=token)


@app.get("/auth/me", response_model=CurrentUserOut)
def current_user(user: AuthUser = Depends(require_user)) -> CurrentUserOut:
    return CurrentUserOut(username=user.username, role=user.role)


@app.get("/users", response_model=list[UserOut])
def get_users(db: Session = Depends(get_db), _user: AuthUser = Depends(require_admin)) -> list[UserOut]:
    return [UserOut(username=user.username, role=user.role, is_active=user.is_active) for user in list_users(db)]


@app.post("/users", response_model=UserOut)
def add_user(payload: UserCreate, db: Session = Depends(get_db), _user: AuthUser = Depends(require_admin)) -> UserOut:
    user = create_user(db, payload.username, payload.password, payload.role, payload.is_active)
    return UserOut(username=user.username, role=user.role, is_active=user.is_active)


@app.patch("/users/{username}", response_model=UserOut)
def edit_user(
    username: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current: AuthUser = Depends(require_admin),
) -> UserOut:
    if username == current.username and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account.")
    user = update_user(db, username, payload.role, payload.is_active, payload.password)
    return UserOut(username=user.username, role=user.role, is_active=user.is_active)


@app.post("/time-entries", response_model=TimeEntryOut)
def add_time_entry(
    payload: TimeEntryCreate,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_editor),
) -> TimeEntryOut:
    return serialize_entry(create_time_entry(db, payload))


@app.get("/time-entries", response_model=list[TimeEntryOut])
def get_time_entries(
    date_from: str | None = None,
    date_to: str | None = None,
    project: str | None = None,
    ticket: str | None = None,
    text: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
) -> list[TimeEntryOut]:
    from datetime import date

    parsed_from = date.fromisoformat(date_from) if date_from else None
    parsed_to = date.fromisoformat(date_to) if date_to else None
    return [
        serialize_entry(entry)
        for entry in list_time_entries(db, parsed_from, parsed_to, project, ticket, text, limit)
    ]


@app.put("/time-entries/{entry_id}", response_model=TimeEntryOut)
def edit_time_entry(
    entry_id: UUID,
    payload: TimeEntryCreate,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_editor),
) -> TimeEntryOut:
    entry = update_time_entry(db, entry_id, payload)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found.")
    return serialize_entry(entry)


@app.delete("/time-entries/{entry_id}")
def remove_time_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_editor),
) -> dict:
    if not delete_time_entry(db, entry_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time entry not found.")
    return {"deleted": True}


@app.get("/time-entries/export.xlsx")
def export_time_entries(
    date_from: str | None = None,
    date_to: str | None = None,
    project: str | None = None,
    ticket: str | None = None,
    text: str | None = None,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_user),
) -> StreamingResponse:
    from datetime import date

    parsed_from = date.fromisoformat(date_from) if date_from else None
    parsed_to = date.fromisoformat(date_to) if date_to else None
    rows = [serialize_entry(entry) for entry in list_time_entries(db, parsed_from, parsed_to, project, ticket, text, 500)]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Aktivity"
    sheet.append([
        "Datum",
        "Den",
        "Od",
        "Do",
        "Zadano",
        "Prekryv",
        "Skutecne",
        "Kategorie",
        "Tiket",
        "Zakazka",
        "Doprava",
        "km",
        "Popis",
        "Zapsano",
    ])
    weekdays = ["Po", "Ut", "St", "Ct", "Pa", "So", "Ne"]
    for row in rows:
        sheet.append([
            row.spent_on.isoformat(),
            weekdays[row.spent_on.weekday()],
            row.started_at.strftime("%H:%M") if row.started_at else "",
            row.ended_at.strftime("%H:%M") if row.ended_at else "",
            float(row.duration_hours),
            float(row.overlap_hours or 0),
            float(row.effective_hours),
            row.category_code or "",
            row.ticket_external_id or "",
            row.project_name or "",
            row.transport_name or "",
            float(row.km) if row.km is not None else "",
            row.description,
            row.reported_status or "",
        ])
    for column in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 10), 60)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="aktivity.xlsx"'},
    )


@app.post("/time-entries/parse-text", response_model=TextEntryParseResponse)
def parse_time_entry_text(
    payload: TextEntryParseRequest,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_editor),
) -> TextEntryParseResponse:
    parsed = parse_text_entry(db, payload.text, payload.spent_on, payload.category_code)
    return TextEntryParseResponse(
        original_text=payload.text,
        draft=parsed["draft"],
        matched_ticket=parsed["matched_ticket"],
        confidence_notes=parsed["confidence_notes"],
    )


@app.get("/fuel/vehicles", response_model=list[FuelVehicleOut])
def get_fuel_vehicles(
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_user),
) -> list[FuelVehicleOut]:
    return [
        FuelVehicleOut(
            id=vehicle.id,
            code=vehicle.code,
            name=vehicle.name,
            is_active=vehicle.is_active,
            sort_order=vehicle.sort_order,
        )
        for vehicle in list_fuel_vehicles(db)
    ]


@app.get("/fuel/entries", response_model=list[FuelEntryOut])
def get_fuel_entries(
    vehicle_id: UUID | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 1000,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_user),
) -> list[FuelEntryOut]:
    from datetime import date

    parsed_from = date.fromisoformat(date_from) if date_from else None
    parsed_to = date.fromisoformat(date_to) if date_to else None
    return [serialize_fuel_entry(entry) for entry in list_fuel_entries(db, vehicle_id, parsed_from, parsed_to, limit)]


@app.get("/fuel/summary", response_model=list[FuelSummaryRow])
def get_fuel_summary(
    vehicle_id: UUID | None = None,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_user),
) -> list[FuelSummaryRow]:
    return [FuelSummaryRow(**row) for row in fuel_summary(db, vehicle_id)]


@app.post("/fuel/parse-photos", response_model=FuelPhotoParseResponse)
async def parse_fuel_entry_photos(
    receipt_photo: UploadFile | None = File(None),
    dashboard_photo: UploadFile | None = File(None),
    _user: AuthUser = Depends(require_editor),
) -> FuelPhotoParseResponse:
    receipt_bytes = await receipt_photo.read() if receipt_photo and receipt_photo.filename else None
    dashboard_bytes = await dashboard_photo.read() if dashboard_photo and dashboard_photo.filename else None
    if not receipt_bytes and not dashboard_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No photo uploaded.")
    try:
        result = parse_fuel_photos(receipt_bytes, dashboard_bytes)
    except FuelOcrUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return FuelPhotoParseResponse(**result)


@app.post("/fuel/entries", response_model=FuelEntryOut)
async def add_fuel_entry(
    vehicle_id: UUID = Form(...),
    purchased_on: str = Form(...),
    purchased_at: str | None = Form(None),
    station: str | None = Form(None),
    fuel_type: str | None = Form(None),
    odometer_km: str | None = Form(None),
    liters: str | None = Form(None),
    total_price_vat: str | None = Form(None),
    total_price_no_vat: str | None = Form(None),
    price_per_liter: str | None = Form(None),
    trip_km: str | None = Form(None),
    full_tank: str | None = Form(None),
    average_consumption: str | None = Form(None),
    note: str | None = Form(None),
    receipt_photo: UploadFile | None = File(None),
    dashboard_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_editor),
) -> FuelEntryOut:
    from datetime import date, time

    prefix = str(uuid4())
    payload = FuelEntryCreate(
        vehicle_id=vehicle_id,
        purchased_on=date.fromisoformat(purchased_on),
        purchased_at=time.fromisoformat(purchased_at) if purchased_at else None,
        station=station,
        fuel_type=fuel_type,
        odometer_km=decimal_or_none(odometer_km),
        liters=decimal_or_none(liters),
        total_price_vat=decimal_or_none(total_price_vat),
        total_price_no_vat=decimal_or_none(total_price_no_vat),
        price_per_liter=decimal_or_none(price_per_liter),
        trip_km=decimal_or_none(trip_km),
        full_tank=bool_or_none(full_tank),
        average_consumption=decimal_or_none(average_consumption),
        note=note,
    )
    entry = create_fuel_entry(
        db,
        payload,
        await save_upload(receipt_photo, f"{prefix}-receipt"),
        await save_upload(dashboard_photo, f"{prefix}-dashboard"),
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vehicle is not active.")
    return serialize_fuel_entry(entry)


@app.put("/fuel/entries/{entry_id}", response_model=FuelEntryOut)
def edit_fuel_entry(
    entry_id: UUID,
    payload: FuelEntryUpdate,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_editor),
) -> FuelEntryOut:
    entry = update_fuel_entry(db, entry_id, payload)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fuel entry not found or vehicle is inactive.")
    return serialize_fuel_entry(entry)


@app.post("/fuel/imports/excel", response_model=FuelImportResponse)
async def import_fuel_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_admin),
) -> FuelImportResponse:
    suffix = Path(file.filename or "phm.xls").suffix or ".xls"
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        result = import_fuel_workbook(db, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return FuelImportResponse(**result)


@app.get("/overhead-tickets", response_model=list[OverheadTicketOut])
def get_overhead_tickets(
    project: str | None = None,
    active_on: str | None = None,
    limit: int = 300,
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
) -> list[OverheadTicketOut]:
    from datetime import date

    parsed_active_on = date.fromisoformat(active_on) if active_on else None
    return [
        OverheadTicketOut(
            external_id=ticket.external_id,
            project_name=ticket.project.name if ticket.project else None,
            subject=ticket.subject,
            source_period=ticket.source_period,
            valid_from=ticket.valid_from,
            valid_to=ticket.valid_to,
        )
        for ticket in list_overhead_tickets(db, project, parsed_active_on, limit)
    ]


@app.patch("/overhead-tickets/validity", response_model=BulkUpdateResponse)
def bulk_update_overhead_ticket_validity(
    payload: OverheadTicketValidityUpdate,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_admin),
) -> BulkUpdateResponse:
    from datetime import datetime, time

    valid_from = datetime.combine(payload.valid_from, time.min) if payload.valid_from else None
    valid_to = datetime.combine(payload.valid_to, time.max) if payload.valid_to else None
    updated_count = update_overhead_ticket_validity(db, payload.external_ids, valid_from, valid_to)
    return BulkUpdateResponse(updated_count=updated_count)


@app.get("/statistics/monthly", response_model=list[SummaryRow])
def get_monthly_summary(
    year: int | None = None,
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
) -> list[SummaryRow]:
    return [SummaryRow(year=int(row.year), month=int(row.month), hours=row.hours) for row in monthly_summary(db, year)]


@app.get("/statistics/projects", response_model=list[ProjectSummaryRow])
def get_project_summary(
    year: int | None = None,
    month: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
) -> list[ProjectSummaryRow]:
    from datetime import date

    parsed_from = date.fromisoformat(date_from) if date_from else None
    parsed_to = date.fromisoformat(date_to) if date_to else None
    return [
        ProjectSummaryRow(project_name=row.project_name, hours=row.hours)
        for row in project_summary(db, year, month, parsed_from, parsed_to)
    ]


@app.get("/statistics/periods", response_model=list[PeriodSummaryRow])
def get_period_summary(
    group_by: str = "month",
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
) -> list[PeriodSummaryRow]:
    from datetime import date

    parsed_from = date.fromisoformat(date_from) if date_from else None
    parsed_to = date.fromisoformat(date_to) if date_to else None
    return [PeriodSummaryRow(**row) for row in period_summary(db, group_by, parsed_from, parsed_to)]


@app.get("/statistics/category-comparison", response_model=CategoryComparisonOut)
def get_category_comparison(
    today: str | None = None,
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
) -> CategoryComparisonOut:
    from datetime import date

    parsed_today = date.fromisoformat(today) if today else date.today()
    return CategoryComparisonOut(**category_comparison(db, parsed_today))


@app.get("/statistics/category-periods", response_model=list[CategoryPeriodRow])
def get_category_periods(
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _user: str = Depends(require_user),
) -> list[CategoryPeriodRow]:
    from datetime import date

    parsed_from = date.fromisoformat(date_from) if date_from else None
    parsed_to = date.fromisoformat(date_to) if date_to else None
    return [CategoryPeriodRow(**row) for row in category_period_summary(db, parsed_from, parsed_to)]


@app.post("/voice/parse", response_model=VoiceParseResponse)
def parse_voice(payload: VoiceParseRequest, _user: AuthUser = Depends(require_editor)) -> VoiceParseResponse:
    draft, notes = parse_voice_text(payload.text)
    return VoiceParseResponse(original_text=payload.text, draft=draft, confidence_notes=notes)


@app.post("/imports/excel")
async def import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_admin),
) -> dict:
    suffix = Path(file.filename or "activities.xlsm").suffix or ".xlsm"
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        result = import_workbook(db, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return result
