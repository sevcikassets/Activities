from datetime import date, datetime, time, timedelta
import calendar
from decimal import Decimal
from unicodedata import normalize

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app import models
from app.schemas import TimeEntryCreate


def normalize_name(value: str) -> str:
    clean = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(clean.lower().split())


def infer_category_code(project_name: str | None) -> str | None:
    if not project_name:
        return None
    project_key = normalize_name(project_name)
    if project_key == "abra vr":
        return "A"
    if project_key == "anglictina":
        return "V"
    if project_key in {"rd kvasice", "investice", "soukrome"}:
        return "S"
    if project_key in {"pohyb", "cviceni"}:
        return "P"
    return None


def get_or_create_project(db: Session, name: str | None) -> models.Project | None:
    if not name:
        return None
    existing = db.scalar(select(models.Project).where(models.Project.name == name))
    if existing:
        return existing
    project = models.Project(name=name, normalized_name=normalize_name(name))
    db.add(project)
    db.flush()
    return project


def get_or_create_ticket(
    db: Session,
    external_id: str | None,
    project: models.Project | None,
    subject: str | None = None,
    is_overhead: bool = False,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    source_period: str | None = None,
) -> models.Ticket | None:
    if not external_id:
        return None
    existing = db.scalar(select(models.Ticket).where(models.Ticket.external_id == external_id))
    if existing:
        return existing
    ticket = models.Ticket(
        external_id=external_id,
        project_id=project.id if project else None,
        subject=subject,
        is_overhead=is_overhead,
        valid_from=valid_from,
        valid_to=valid_to,
        source_period=source_period,
    )
    db.add(ticket)
    db.flush()
    return ticket


def find_valid_overhead_ticket(
    db: Session,
    project_name: str | None,
    spent_on: date,
    started_at: time | None = None,
) -> models.Ticket | None:
    if not project_name:
        return None
    project_key = normalize_name(project_name)
    moment = datetime.combine(spent_on, started_at or time.min)
    stmt = (
        select(models.Ticket)
        .join(models.Project, models.Project.id == models.Ticket.project_id, isouter=True)
        .where(
            models.Ticket.is_overhead.is_(True),
            models.Project.normalized_name == project_key,
            or_(models.Ticket.valid_from.is_(None), models.Ticket.valid_from <= moment),
            or_(models.Ticket.valid_to.is_(None), models.Ticket.valid_to >= moment),
        )
        .order_by(models.Ticket.valid_from.desc().nullslast(), models.Ticket.external_id.desc())
        .limit(1)
    )
    return db.scalar(stmt)


def get_or_create_category(db: Session, code: str | None) -> str | None:
    if not code:
        return None
    existing = db.scalar(select(models.Category).where(models.Category.code == code))
    if existing:
        return existing.code
    db.add(models.Category(code=code, name=code))
    db.flush()
    return code


def get_or_create_transport(db: Session, name: str | None) -> models.Transport | None:
    if not name:
        return None
    existing = db.scalar(select(models.Transport).where(models.Transport.name == name))
    if existing:
        return existing
    transport = models.Transport(name=name)
    db.add(transport)
    db.flush()
    return transport


def calculate_overlap_hours(db: Session, payload: TimeEntryCreate) -> Decimal:
    if not payload.started_at or not payload.ended_at:
        return Decimal("0")

    def to_minutes(value: time) -> int:
        return value.hour * 60 + value.minute

    start = to_minutes(payload.started_at)
    end = to_minutes(payload.ended_at)
    if end < start:
        end += 24 * 60

    intervals: list[tuple[int, int]] = []
    existing_entries = db.scalars(
        select(models.TimeEntry).where(
            models.TimeEntry.spent_on == payload.spent_on,
            models.TimeEntry.started_at.is_not(None),
            models.TimeEntry.ended_at.is_not(None),
        )
    ).all()
    for entry in existing_entries:
        existing_start = to_minutes(entry.started_at)
        existing_end = to_minutes(entry.ended_at)
        if existing_end < existing_start:
            existing_end += 24 * 60
        overlap_start = max(start, existing_start)
        overlap_end = min(end, existing_end)
        if overlap_end > overlap_start:
            intervals.append((overlap_start, overlap_end))

    if not intervals:
        return Decimal("0")

    intervals.sort()
    merged: list[list[int]] = []
    for interval_start, interval_end in intervals:
        if not merged or interval_start > merged[-1][1]:
            merged.append([interval_start, interval_end])
        else:
            merged[-1][1] = max(merged[-1][1], interval_end)

    overlap_minutes = sum(interval_end - interval_start for interval_start, interval_end in merged)
    return Decimal(str(round(overlap_minutes / 60, 2)))


def calculate_duration_hours(payload: TimeEntryCreate) -> Decimal:
    if not payload.started_at or not payload.ended_at:
        return payload.duration_hours

    start_dt = datetime.combine(payload.spent_on, payload.started_at)
    end_dt = datetime.combine(payload.spent_on, payload.ended_at)
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    return Decimal(str(round((end_dt - start_dt).total_seconds() / 3600, 2)))


def calculate_overlap_hours_for_entry(db: Session, entry_id, payload: TimeEntryCreate) -> Decimal:
    if not payload.started_at or not payload.ended_at:
        return Decimal("0")

    def to_minutes(value: time) -> int:
        return value.hour * 60 + value.minute

    start = to_minutes(payload.started_at)
    end = to_minutes(payload.ended_at)
    if end < start:
        end += 24 * 60

    intervals: list[tuple[int, int]] = []
    existing_entries = db.scalars(
        select(models.TimeEntry).where(
            models.TimeEntry.id != entry_id,
            models.TimeEntry.spent_on == payload.spent_on,
            models.TimeEntry.started_at.is_not(None),
            models.TimeEntry.ended_at.is_not(None),
        )
    ).all()
    for entry in existing_entries:
        existing_start = to_minutes(entry.started_at)
        existing_end = to_minutes(entry.ended_at)
        if existing_end < existing_start:
            existing_end += 24 * 60
        overlap_start = max(start, existing_start)
        overlap_end = min(end, existing_end)
        if overlap_end > overlap_start:
            intervals.append((overlap_start, overlap_end))

    if not intervals:
        return Decimal("0")

    intervals.sort()
    merged: list[list[int]] = []
    for interval_start, interval_end in intervals:
        if not merged or interval_start > merged[-1][1]:
            merged.append([interval_start, interval_end])
        else:
            merged[-1][1] = max(merged[-1][1], interval_end)

    overlap_minutes = sum(interval_end - interval_start for interval_start, interval_end in merged)
    return Decimal(str(round(overlap_minutes / 60, 2)))


def create_time_entry(db: Session, payload: TimeEntryCreate, source: str = "manual") -> models.TimeEntry:
    project = get_or_create_project(db, payload.project_name)
    ticket = get_or_create_ticket(db, payload.ticket_external_id, project)
    if ticket is None:
        ticket = find_valid_overhead_ticket(db, payload.project_name, payload.spent_on, payload.started_at)
    category_code = get_or_create_category(db, payload.category_code or infer_category_code(payload.project_name))
    transport = get_or_create_transport(db, payload.transport_name)
    overlap_hours = calculate_overlap_hours(db, payload)
    duration_hours = calculate_duration_hours(payload)
    entry = models.TimeEntry(
        spent_on=payload.spent_on,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_hours=duration_hours,
        category_code=category_code,
        description=payload.description,
        ticket_id=ticket.id if ticket else None,
        project_id=project.id if project else None,
        transport_id=transport.id if transport else None,
        km=payload.km,
        overlap_hours=overlap_hours,
        redmine_time=payload.redmine_time,
        reported_status=payload.reported_status,
        source=source,
        raw_text=payload.raw_text,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_time_entry(db: Session, entry_id, payload: TimeEntryCreate) -> models.TimeEntry | None:
    entry = db.scalar(
        select(models.TimeEntry)
        .options(
            joinedload(models.TimeEntry.project),
            joinedload(models.TimeEntry.ticket),
            joinedload(models.TimeEntry.transport),
        )
        .where(models.TimeEntry.id == entry_id)
    )
    if not entry:
        return None

    project = get_or_create_project(db, payload.project_name)
    ticket = get_or_create_ticket(db, payload.ticket_external_id, project)
    if ticket is None:
        ticket = find_valid_overhead_ticket(db, payload.project_name, payload.spent_on, payload.started_at)
    category_code = get_or_create_category(db, payload.category_code or infer_category_code(payload.project_name))
    transport = get_or_create_transport(db, payload.transport_name)

    entry.spent_on = payload.spent_on
    entry.started_at = payload.started_at
    entry.ended_at = payload.ended_at
    entry.duration_hours = calculate_duration_hours(payload)
    entry.category_code = category_code
    entry.description = payload.description
    entry.ticket_id = ticket.id if ticket else None
    entry.project_id = project.id if project else None
    entry.transport_id = transport.id if transport else None
    entry.km = payload.km
    entry.overlap_hours = calculate_overlap_hours_for_entry(db, entry_id, payload)
    entry.redmine_time = payload.redmine_time
    entry.reported_status = payload.reported_status
    entry.raw_text = payload.raw_text
    entry.updated_at = datetime.now()
    db.commit()
    db.refresh(entry)
    return entry


def delete_time_entry(db: Session, entry_id) -> bool:
    entry = db.scalar(select(models.TimeEntry).where(models.TimeEntry.id == entry_id))
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    return True


def list_time_entries(
    db: Session,
    date_from: date | None = None,
    date_to: date | None = None,
    project: str | None = None,
    ticket: str | None = None,
    text: str | None = None,
    limit: int = 200,
):
    stmt = (
        select(models.TimeEntry)
        .options(
            joinedload(models.TimeEntry.project),
            joinedload(models.TimeEntry.ticket),
            joinedload(models.TimeEntry.transport),
        )
        .join(models.Project, models.Project.id == models.TimeEntry.project_id, isouter=True)
        .join(models.Ticket, models.Ticket.id == models.TimeEntry.ticket_id, isouter=True)
        .order_by(models.TimeEntry.spent_on.desc(), models.TimeEntry.started_at.asc().nullslast())
        .limit(min(limit, 500))
    )
    if date_from:
        stmt = stmt.where(models.TimeEntry.spent_on >= date_from)
    if date_to:
        stmt = stmt.where(models.TimeEntry.spent_on <= date_to)
    if project:
        stmt = stmt.where(models.Project.name.ilike(f"%{project}%"))
    if ticket:
        stmt = stmt.where(models.Ticket.external_id.ilike(f"%{ticket}%"))
    if text:
        stmt = stmt.where(models.TimeEntry.description.ilike(f"%{text}%"))
    return db.scalars(stmt).all()


def list_overhead_tickets(db: Session, project: str | None = None, active_on: date | None = None, limit: int = 300):
    stmt = (
        select(models.Ticket)
        .options(joinedload(models.Ticket.project))
        .join(models.Project, models.Project.id == models.Ticket.project_id, isouter=True)
        .where(models.Ticket.is_overhead.is_(True))
        .order_by(models.Project.name, models.Ticket.valid_from.desc().nullslast(), models.Ticket.external_id.desc())
        .limit(min(limit, 1000))
    )
    if project:
        stmt = stmt.where(models.Project.name.ilike(f"%{project}%"))
    if active_on:
        start = datetime.combine(active_on, time.min)
        end = datetime.combine(active_on, time.max)
        stmt = stmt.where(
            and_(
                or_(models.Ticket.valid_from.is_(None), models.Ticket.valid_from <= end),
                or_(models.Ticket.valid_to.is_(None), models.Ticket.valid_to >= start),
            )
        )
    return db.scalars(stmt).all()


def update_overhead_ticket_validity(
    db: Session,
    external_ids: list[str],
    valid_from: datetime | None,
    valid_to: datetime | None,
) -> int:
    if not external_ids:
        return 0
    tickets = db.scalars(
        select(models.Ticket).where(
            models.Ticket.is_overhead.is_(True),
            models.Ticket.external_id.in_(external_ids),
        )
    ).all()
    for ticket in tickets:
        ticket.valid_from = valid_from
        ticket.valid_to = valid_to
    db.commit()
    return len(tickets)


def parse_text_entry(db: Session, raw_text: str, spent_on: date | None = None, category_code: str | None = None):
    import re

    notes: list[str] = []
    text = " ".join(raw_text.strip().split())
    pattern = re.compile(
        r"^(?P<from>\d{1,2}[:.]\d{2})\s*-\s*(?P<to>\d{1,2}[:.-]\d{2})\s*:\s*(?P<description>.+?)\s+Z:\s*(?P<project>.+)$",
        re.IGNORECASE,
    )
    match = pattern.match(text)
    if not match:
        return {
            "draft": {"spent_on": (spent_on or date.today()).isoformat(), "description": text, "raw_text": text},
            "matched_ticket": None,
            "confidence_notes": ["Text neodpovida formatu HH:MM-HH:MM: text Z: zakazka."],
        }

    def parse_clock(value: str) -> time:
        hour, minute = value.replace(".", ":").replace("-", ":").split(":", 1)
        return time(int(hour), int(minute))

    start = parse_clock(match.group("from"))
    end = parse_clock(match.group("to"))
    entry_date = spent_on or date.today()
    start_dt = datetime.combine(entry_date, start)
    end_dt = datetime.combine(entry_date, end)
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    duration = Decimal(str(round((end_dt - start_dt).total_seconds() / 3600, 2)))
    project_name = match.group("project").strip()
    km_value: str | None = None
    km_match = re.search(r"\s*-\s*(?P<km>\d+(?:[,.]\d+)?)$", project_name)
    if km_match:
        km_value = km_match.group("km").replace(",", ".")
        project_name = project_name[: km_match.start()].strip()
    resolved_category = category_code or infer_category_code(project_name)
    ticket = find_valid_overhead_ticket(db, project_name, entry_date, start)
    if not ticket:
        notes.append("Pro zakazku a datum/cas nebyl nalezen platny rezijni tiket.")
    description = match.group("description").strip()
    normalized_text = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}: {description} Z: {project_name}"
    draft = {
        "spent_on": entry_date.isoformat(),
        "started_at": start.strftime("%H:%M"),
        "ended_at": end.strftime("%H:%M"),
        "duration_hours": str(duration),
        "category_code": resolved_category,
        "description": normalized_text,
        "project_name": project_name,
        "ticket_external_id": ticket.external_id if ticket else None,
        "raw_text": description,
    }
    if km_value:
        draft["km"] = km_value
    if "cesta" in normalize_name(description):
        draft["transport_name"] = "Volvo XC90"
    return {
        "draft": draft,
        "matched_ticket": {
            "external_id": ticket.external_id,
            "project_name": ticket.project.name if ticket.project else None,
            "subject": ticket.subject,
            "valid_from": ticket.valid_from,
            "valid_to": ticket.valid_to,
        }
        if ticket
        else None,
        "confidence_notes": notes,
    }


def monthly_summary(db: Session, year: int | None = None):
    stmt = (
        select(
            func.extract("year", models.TimeEntry.spent_on).label("year"),
            func.extract("month", models.TimeEntry.spent_on).label("month"),
            func.coalesce(func.sum(models.TimeEntry.duration_hours), Decimal("0")).label("hours"),
        )
        .group_by("year", "month")
        .order_by("year", "month")
    )
    if year:
        stmt = stmt.where(func.extract("year", models.TimeEntry.spent_on) == year)
    return db.execute(stmt).all()


def project_summary(
    db: Session,
    year: int | None = None,
    month: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    stmt = (
        select(
            func.coalesce(models.Project.name, "(bez projektu)").label("project_name"),
            func.coalesce(func.sum(models.TimeEntry.duration_hours), Decimal("0")).label("hours"),
        )
        .join(models.Project, models.Project.id == models.TimeEntry.project_id, isouter=True)
        .group_by(models.Project.name)
        .order_by(func.sum(models.TimeEntry.duration_hours).desc())
    )
    if year:
        stmt = stmt.where(func.extract("year", models.TimeEntry.spent_on) == year)
    if month:
        stmt = stmt.where(func.extract("month", models.TimeEntry.spent_on) == month)
    if date_from:
        stmt = stmt.where(models.TimeEntry.spent_on >= date_from)
    if date_to:
        stmt = stmt.where(models.TimeEntry.spent_on <= date_to)
    return db.execute(stmt).all()


def period_summary(
    db: Session,
    group_by: str,
    date_from: date | None = None,
    date_to: date | None = None,
):
    rows = db.execute(
        select(
            models.TimeEntry.spent_on,
            func.coalesce(func.sum(models.TimeEntry.duration_hours), Decimal("0")).label("hours"),
        )
        .where(models.TimeEntry.spent_on >= date_from if date_from else True)
        .where(models.TimeEntry.spent_on <= date_to if date_to else True)
        .group_by(models.TimeEntry.spent_on)
        .order_by(models.TimeEntry.spent_on)
    ).all()

    grouped: dict[str, dict] = {}
    for row in rows:
        spent_on: date = row.spent_on
        if group_by == "day":
            start = spent_on
            end = spent_on
            key = spent_on.isoformat()
            label = spent_on.isoformat()
        elif group_by == "week":
            start = spent_on - timedelta(days=spent_on.weekday())
            end = start + timedelta(days=6)
            iso_year, iso_week, _ = spent_on.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            label = key
        elif group_by == "month":
            start = spent_on.replace(day=1)
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = next_month - timedelta(days=1)
            key = start.strftime("%Y-%m")
            label = key
        elif group_by == "year":
            start = spent_on.replace(month=1, day=1)
            end = spent_on.replace(month=12, day=31)
            key = str(spent_on.year)
            label = key
        else:
            raise ValueError("Unsupported group_by value.")

        item = grouped.setdefault(
            key,
            {"period_key": key, "period_label": label, "date_from": start, "date_to": end, "hours": Decimal("0")},
        )
        item["hours"] += row.hours

    return list(grouped.values())


def category_period_summary(
    db: Session,
    date_from: date | None = None,
    date_to: date | None = None,
):
    effective = models.TimeEntry.duration_hours - func.coalesce(models.TimeEntry.overlap_hours, Decimal("0"))
    rows = db.execute(
        select(
            models.TimeEntry.spent_on,
            models.TimeEntry.category_code,
            func.coalesce(func.sum(effective), Decimal("0")).label("hours"),
        )
        .where(models.TimeEntry.spent_on >= date_from if date_from else True)
        .where(models.TimeEntry.spent_on <= date_to if date_to else True)
        .group_by(models.TimeEntry.spent_on, models.TimeEntry.category_code)
        .order_by(models.TimeEntry.spent_on)
    ).all()

    grouped: dict[str, dict] = {}
    for row in rows:
        spent_on: date = row.spent_on
        start = spent_on.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month - timedelta(days=1)
        key = start.strftime("%Y-%m")
        item = grouped.setdefault(
            key,
            {
                "period_key": key,
                "period_label": key,
                "date_from": start,
                "date_to": end,
                "abra_hours": Decimal("0"),
                "education_hours": Decimal("0"),
                "private_hours": Decimal("0"),
                "movement_hours": Decimal("0"),
                "tanaka_hours": Decimal("0"),
                "total_hours": Decimal("0"),
            },
        )
        category_code = row.category_code
        if category_code == "A":
            item["abra_hours"] += row.hours
        elif category_code == "V":
            item["education_hours"] += row.hours
        elif category_code == "S":
            item["private_hours"] += row.hours
        elif category_code == "P":
            item["movement_hours"] += row.hours
        elif category_code is None:
            item["tanaka_hours"] += row.hours
        item["total_hours"] += row.hours

    return list(grouped.values())


def category_comparison(db: Session, today: date):
    week_start = today - timedelta(days=today.weekday())
    previous_week_start = week_start - timedelta(days=7)
    previous_week_end = previous_week_start + (today - week_start)

    month_start = today.replace(day=1)
    previous_month_year = today.year if today.month > 1 else today.year - 1
    previous_month = today.month - 1 if today.month > 1 else 12
    previous_month_last_day = calendar.monthrange(previous_month_year, previous_month)[1]
    previous_month_end_day = min(today.day, previous_month_last_day)
    previous_month_start = date(previous_month_year, previous_month, 1)
    previous_month_end = date(previous_month_year, previous_month, previous_month_end_day)

    categories = [
        ("A", "ABRA", "A"),
        ("V", "Vzdelavani", "V"),
        ("S", "Soukrome", "S"),
        ("P", "Pohyb", "P"),
        ("tanaka", "TANAKA", None),
    ]

    def hours_for(category_code: str | None, date_from: date, date_to: date) -> Decimal:
        effective = models.TimeEntry.duration_hours - func.coalesce(models.TimeEntry.overlap_hours, Decimal("0"))
        stmt = select(func.coalesce(func.sum(effective), Decimal("0"))).where(
            models.TimeEntry.spent_on >= date_from,
            models.TimeEntry.spent_on <= date_to,
        )
        if category_code is None:
            stmt = stmt.where(models.TimeEntry.category_code.is_(None))
        else:
            stmt = stmt.where(models.TimeEntry.category_code == category_code)
        return db.scalar(stmt) or Decimal("0")

    rows = []
    for key, label, category_code in categories:
        current_week = hours_for(category_code, week_start, today)
        previous_week = hours_for(category_code, previous_week_start, previous_week_end)
        current_month = hours_for(category_code, month_start, today)
        previous_month_period = hours_for(category_code, previous_month_start, previous_month_end)
        rows.append(
            {
                "category_key": key,
                "label": label,
                "current_week_hours": current_week,
                "previous_week_hours": previous_week,
                "week_delta_hours": current_week - previous_week,
                "current_month_hours": current_month,
                "previous_month_same_period_hours": previous_month_period,
                "month_delta_hours": current_month - previous_month_period,
            }
        )

    return {
        "today": today,
        "current_week_from": week_start,
        "current_week_to": today,
        "previous_week_from": previous_week_start,
        "previous_week_to": previous_week_end,
        "current_month_from": month_start,
        "current_month_to": today,
        "previous_month_from": previous_month_start,
        "previous_month_to": previous_month_end,
        "rows": rows,
    }
