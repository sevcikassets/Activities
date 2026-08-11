from pathlib import Path
from decimal import Decimal
from tempfile import NamedTemporaryFile

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import models
from app.auth import AuthUser, authenticate, bootstrap_admin_user, create_user, list_users, require_admin, require_editor, require_user, update_user
from app.config import settings
from app.db import SessionLocal, get_db
from app.excel_import import import_workbook
from app.repository import (
    category_comparison,
    category_period_summary,
    create_time_entry,
    list_overhead_tickets,
    list_time_entries,
    monthly_summary,
    parse_text_entry,
    period_summary,
    project_summary,
    update_overhead_ticket_validity,
)
from app.schemas import (
    BulkUpdateResponse,
    CategoryComparisonOut,
    CategoryPeriodRow,
    CurrentUserOut,
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


app = FastAPI(title="Activities API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    with SessionLocal() as db:
        bootstrap_admin_user(db)


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    token = authenticate(db, payload.username, payload.password)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
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
