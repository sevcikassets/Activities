from datetime import date, datetime, time, timedelta
import calendar
from decimal import Decimal
import re
from unicodedata import normalize

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, joinedload

from app import models
from app.schemas import TimeEntryCreate


FUEL_VEHICLES = [
    ("volvo-xc90", "Volvo", True, 1, ["EL6 14DE XC90"]),
    ("skoda-felicie", "Skoda Felicie", False, 2, ["ZLI 89-51 Natural 95", "ZLI 89-51 LPG"]),
    ("audi-a6", "Audi A6", False, 3, ["5Z0 9004 AUDI"]),
    ("vw-passat", "VW Passat", False, 4, ["2Z4 3277 Passat"]),
    ("bmw", "BMW", False, 5, ["6AP 0033 BMW"]),
]


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


def clean_activity_description(value: str, project_name: str | None = None) -> str:
    cleaned = " ".join(value.strip().split())
    cleaned = re.sub(r"^\d{1,2}[:.]\d{2}\s*-\s*\d{1,2}[:.-]\d{2}\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    if project_name:
        escaped_project = re.escape(project_name.strip())
        cleaned = re.sub(rf"\s+Z:\s*{escaped_project}(?:\s*-\s*\d+(?:[,.]\d+)?)?\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+Z:\s*.+?(?:\s*-\s*\d+(?:[,.]\d+)?)?\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def normalize_time_entry_descriptions(db: Session) -> int:
    entries = db.scalars(
        select(models.TimeEntry)
        .options(joinedload(models.TimeEntry.project))
        .where(
            or_(
                models.TimeEntry.description.op("~*")(r"^\d{1,2}[:.]\d{2}\s*-\s*\d{1,2}[:.-]\d{2}\s*:"),
                models.TimeEntry.description.op("~*")(r"\s+Z:\s*.+?(\s*-\s*\d+([,.]\d+)?)?\s*$"),
            )
        )
    ).all()
    updated_count = 0
    for entry in entries:
        original_description = entry.description
        cleaned = clean_activity_description(entry.description, entry.project.name if entry.project else None)
        if cleaned and cleaned != original_description:
            entry.description = cleaned
            if not entry.raw_text or entry.raw_text == original_description:
                entry.raw_text = cleaned
            updated_count += 1
    if updated_count:
        db.commit()
    return updated_count


def ensure_fuel_schema(db: Session) -> None:
    Base = models.FuelVehicle.metadata
    Base.create_all(db.get_bind(), tables=[models.FuelVehicle.__table__, models.FuelEntry.__table__])
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_fuel_entries_vehicle_date ON fuel_entries(vehicle_id, purchased_on)"))
    db.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_fuel_entries_source_row "
            "ON fuel_entries(source, source_sheet, source_row) "
            "WHERE source = 'excel' AND source_sheet IS NOT NULL AND source_row IS NOT NULL"
        )
    )
    db.commit()


def seed_fuel_vehicles(db: Session) -> None:
    for code, name, is_active, sort_order, source_sheets in FUEL_VEHICLES:
        vehicle = db.scalar(select(models.FuelVehicle).where(models.FuelVehicle.code == code))
        if vehicle:
            vehicle.name = name
            vehicle.is_active = is_active
            vehicle.sort_order = sort_order
            vehicle.source_sheets = source_sheets
        else:
            db.add(
                models.FuelVehicle(
                    code=code,
                    name=name,
                    is_active=is_active,
                    sort_order=sort_order,
                    source_sheets=source_sheets,
                )
            )
    db.commit()


def list_fuel_vehicles(db: Session):
    return db.scalars(select(models.FuelVehicle).order_by(models.FuelVehicle.sort_order, models.FuelVehicle.name)).all()


def get_fuel_vehicle(db: Session, vehicle_id):
    return db.scalar(select(models.FuelVehicle).where(models.FuelVehicle.id == vehicle_id))


def list_fuel_entries(db: Session, vehicle_id=None, date_from: date | None = None, date_to: date | None = None, limit: int = 1000):
    stmt = (
        select(models.FuelEntry)
        .options(joinedload(models.FuelEntry.vehicle))
        .order_by(models.FuelEntry.purchased_on.desc(), models.FuelEntry.purchased_at.desc().nullslast())
        .limit(min(limit, 10000))
    )
    if vehicle_id:
        stmt = stmt.where(models.FuelEntry.vehicle_id == vehicle_id)
    if date_from:
        stmt = stmt.where(models.FuelEntry.purchased_on >= date_from)
    if date_to:
        stmt = stmt.where(models.FuelEntry.purchased_on <= date_to)
    return db.scalars(stmt).all()


def create_fuel_entry(db: Session, payload, receipt_photo_path: str | None = None, dashboard_photo_path: str | None = None):
    vehicle = get_fuel_vehicle(db, payload.vehicle_id)
    if not vehicle or not vehicle.is_active:
        return None
    normalized = _fuel_payload_with_calculations(db, payload.vehicle_id, payload)
    entry = models.FuelEntry(
        vehicle_id=normalized["vehicle_id"],
        purchased_on=normalized["purchased_on"],
        purchased_at=normalized["purchased_at"],
        station=normalized["station"],
        fuel_type=normalized["fuel_type"],
        odometer_km=normalized["odometer_km"],
        liters=normalized["liters"],
        total_price_vat=normalized["total_price_vat"],
        total_price_no_vat=normalized["total_price_no_vat"],
        price_per_liter=normalized["price_per_liter"],
        trip_km=normalized["trip_km"],
        full_tank=normalized["full_tank"],
        average_consumption=normalized["average_consumption"],
        note=normalized["note"],
        receipt_photo_path=receipt_photo_path,
        dashboard_photo_path=dashboard_photo_path,
        source="manual",
    )
    db.add(entry)
    db.commit()
    recalculate_fuel_vehicle(db, payload.vehicle_id)
    db.refresh(entry)
    return entry


def update_fuel_entry(db: Session, entry_id, payload):
    entry = db.scalar(
        select(models.FuelEntry)
        .options(joinedload(models.FuelEntry.vehicle))
        .where(models.FuelEntry.id == entry_id)
    )
    if not entry:
        return None
    vehicle_id = payload.vehicle_id or entry.vehicle_id
    vehicle = get_fuel_vehicle(db, vehicle_id)
    if not vehicle or not vehicle.is_active:
        return None
    changed_fields = payload.model_fields_set
    for field in [
        "purchased_on",
        "purchased_at",
        "station",
        "fuel_type",
        "odometer_km",
        "liters",
        "total_price_vat",
        "total_price_no_vat",
        "price_per_liter",
        "trip_km",
        "full_tank",
        "average_consumption",
        "note",
    ]:
        if field not in changed_fields:
            continue
        value = getattr(payload, field)
        setattr(entry, field, value)
    entry.vehicle_id = vehicle_id
    _apply_fuel_entry_calculations(db, entry)
    entry.updated_at = datetime.now()
    db.commit()
    recalculate_fuel_vehicle(db, vehicle_id)
    db.refresh(entry)
    return entry


def _fuel_payload_with_calculations(db: Session, vehicle_id, payload) -> dict:
    values = {
        field: getattr(payload, field)
        for field in [
            "vehicle_id",
            "purchased_on",
            "purchased_at",
            "station",
            "fuel_type",
            "odometer_km",
            "liters",
            "total_price_vat",
            "total_price_no_vat",
            "price_per_liter",
            "trip_km",
            "full_tank",
            "average_consumption",
            "note",
        ]
    }
    values["vehicle_id"] = vehicle_id
    if values["total_price_vat"] is None and values["liters"] and values["price_per_liter"]:
        values["total_price_vat"] = _round_decimal(values["liters"] * values["price_per_liter"])
    if values["price_per_liter"] is None and values["liters"] and values["total_price_vat"]:
        values["price_per_liter"] = _round_decimal(values["total_price_vat"] / values["liters"])
    if values["trip_km"] is None and values["odometer_km"]:
        previous = _previous_fuel_entry(db, vehicle_id, values["purchased_on"], values["purchased_at"])
        if previous and previous.odometer_km and values["odometer_km"] > previous.odometer_km:
            values["trip_km"] = values["odometer_km"] - previous.odometer_km
    if values["full_tank"] is not True:
        values["average_consumption"] = None
    elif values["average_consumption"] is None and values["liters"] and values["trip_km"]:
        values["average_consumption"] = _average_consumption(values["liters"], values["trip_km"])
    return values


def _apply_fuel_entry_calculations(db: Session, entry: models.FuelEntry) -> None:
    if entry.total_price_vat is None and entry.liters and entry.price_per_liter:
        entry.total_price_vat = _round_decimal(entry.liters * entry.price_per_liter)
    if entry.price_per_liter is None and entry.liters and entry.total_price_vat:
        entry.price_per_liter = _round_decimal(entry.total_price_vat / entry.liters)
    if entry.trip_km is None and entry.odometer_km:
        previous = _previous_fuel_entry(db, entry.vehicle_id, entry.purchased_on, entry.purchased_at, entry.id)
        if previous and previous.odometer_km and entry.odometer_km > previous.odometer_km:
            entry.trip_km = entry.odometer_km - previous.odometer_km
    if entry.full_tank is not True:
        entry.average_consumption = None


def _previous_fuel_entry(db: Session, vehicle_id, purchased_on: date, purchased_at: time | None = None, exclude_id=None):
    current_time = purchased_at or time(23, 59, 59)
    stmt = (
        select(models.FuelEntry)
        .where(
            models.FuelEntry.vehicle_id == vehicle_id,
            or_(
                models.FuelEntry.purchased_on < purchased_on,
                and_(
                    models.FuelEntry.purchased_on == purchased_on,
                    func.coalesce(models.FuelEntry.purchased_at, time(0, 0, 0)) < current_time,
                ),
            ),
        )
        .order_by(models.FuelEntry.purchased_on.desc(), models.FuelEntry.purchased_at.desc().nullslast())
        .limit(1)
    )
    if exclude_id:
        stmt = stmt.where(models.FuelEntry.id != exclude_id)
    return db.scalar(stmt)


def recalculate_fuel_vehicle(db: Session, vehicle_id) -> None:
    rows = db.scalars(
        select(models.FuelEntry)
        .where(models.FuelEntry.vehicle_id == vehicle_id)
        .order_by(models.FuelEntry.purchased_on, models.FuelEntry.purchased_at.nullsfirst(), models.FuelEntry.created_at)
    ).all()
    previous_odometer = None
    previous_full_odometer = None
    liters_since_full = Decimal("0")
    for entry in rows:
        if entry.total_price_vat is None and entry.liters and entry.price_per_liter:
            entry.total_price_vat = _round_decimal(entry.liters * entry.price_per_liter)
        if entry.price_per_liter is None and entry.liters and entry.total_price_vat:
            entry.price_per_liter = _round_decimal(entry.total_price_vat / entry.liters)
        if previous_odometer is not None and entry.odometer_km and entry.odometer_km > previous_odometer:
            entry.trip_km = entry.odometer_km - previous_odometer
        elif entry.trip_km is not None and entry.trip_km < 0:
            entry.trip_km = None
        if entry.liters:
            liters_since_full += entry.liters
        if entry.full_tank is True:
            km_since_full = None
            if previous_full_odometer is not None and entry.odometer_km and entry.odometer_km > previous_full_odometer:
                km_since_full = entry.odometer_km - previous_full_odometer
            elif entry.trip_km:
                km_since_full = entry.trip_km
            entry.average_consumption = _average_consumption(liters_since_full, km_since_full) if km_since_full else None
            previous_full_odometer = entry.odometer_km or previous_full_odometer
            liters_since_full = Decimal("0")
        else:
            entry.average_consumption = None
        if entry.odometer_km:
            previous_odometer = entry.odometer_km
    db.commit()


def _round_decimal(value: Decimal, places: str = "0.01") -> Decimal:
    return value.quantize(Decimal(places))


def fuel_summary(db: Session, vehicle_id=None):
    rows = list_fuel_entries(db, vehicle_id, limit=10000)

    earliest_per_vehicle: dict = {}
    for entry in rows:
        entry_key = (entry.purchased_on, entry.purchased_at or time(0, 0, 0))
        current = earliest_per_vehicle.get(entry.vehicle_id)
        if current is None or entry_key < current[0]:
            earliest_per_vehicle[entry.vehicle_id] = (entry_key, entry.id)
    first_entry_ids = {value[1] for value in earliest_per_vehicle.values()}

    monthly: dict[str, dict] = {}
    yearly: dict[str, dict] = {}

    def add_item(target: dict[str, dict], key: str, label: str, level: str, entry) -> None:
        item = target.setdefault(
            key,
            {
                "period_key": key,
                "period_label": label,
                "level": level,
                "liters": Decimal("0"),
                "total_price_vat": Decimal("0"),
                "trip_km": Decimal("0"),
            },
        )
        item["liters"] += entry.liters or Decimal("0")
        item["total_price_vat"] += entry.total_price_vat or Decimal("0")
        item["trip_km"] += entry.trip_km or Decimal("0")

    for entry in rows:
        if entry.id in first_entry_ids:
            continue
        month_key = entry.purchased_on.strftime("%Y-%m")
        year_key = str(entry.purchased_on.year)
        add_item(monthly, month_key, month_key, "month", entry)
        add_item(yearly, year_key, year_key, "year", entry)

    result = []
    for item in sorted(monthly.values(), key=lambda value: value["period_key"], reverse=True):
        result.append({**item, "average_consumption": _average_consumption(item["liters"], item["trip_km"])})
    for item in sorted(yearly.values(), key=lambda value: value["period_key"], reverse=True):
        result.append({**item, "period_label": f"Soucet {item['period_label']}", "average_consumption": _average_consumption(item["liters"], item["trip_km"])})
    return result


def _average_consumption(liters: Decimal, trip_km: Decimal) -> Decimal | None:
    if not trip_km:
        return None
    return Decimal(str(round(float(liters) / float(trip_km) * 100, 2)))


def import_fuel_workbook(db: Session, workbook_path) -> dict:
    import xlrd

    vehicles_by_sheet = {}
    for vehicle in list_fuel_vehicles(db):
        for sheet_name in vehicle.source_sheets or []:
            vehicles_by_sheet[sheet_name] = vehicle

    workbook = xlrd.open_workbook(str(workbook_path))
    imported_rows = 0
    skipped_rows = 0
    for sheet in workbook.sheets():
        vehicle = vehicles_by_sheet.get(sheet.name)
        if not vehicle:
            continue
        header_row = _find_fuel_header_row(sheet)
        if header_row is None:
            skipped_rows += sheet.nrows
            continue
        layout = _fuel_sheet_layout(sheet, header_row, sheet.name)
        for row_index in range(header_row + 1, sheet.nrows):
            parsed_date = _xlrd_date(sheet.cell(row_index, layout["date"]), workbook.datemode)
            if not parsed_date:
                continue
            station = _xlrd_text(sheet.cell(row_index, layout["station"]))
            source_fuel_type = _xlrd_text(sheet.cell(row_index, layout["fuel_type"])) if layout.get("fuel_type") is not None else None
            fuel_type = source_fuel_type or layout.get("default_fuel_type")
            odometer_km = _xlrd_decimal(sheet.cell(row_index, layout["odometer"]))
            liters = _xlrd_decimal(sheet.cell(row_index, layout["liters"]))
            total_price_vat = _xlrd_decimal(sheet.cell(row_index, layout["total_price_vat"]))
            trip_km = _xlrd_decimal(sheet.cell(row_index, layout["trip_km"]))
            if not any([station, source_fuel_type, odometer_km, liters, total_price_vat, trip_km]):
                skipped_rows += 1
                continue
            if db.scalar(
                select(models.FuelEntry).where(
                    models.FuelEntry.source == "excel",
                    models.FuelEntry.source_sheet == sheet.name,
                    models.FuelEntry.source_row == row_index + 1,
                )
            ):
                skipped_rows += 1
                continue
            entry = models.FuelEntry(
                vehicle_id=vehicle.id,
                purchased_on=parsed_date,
                purchased_at=_xlrd_time(sheet.cell(row_index, layout["time"]), workbook.datemode) if layout.get("time") is not None else None,
                station=station,
                fuel_type=fuel_type,
                odometer_km=odometer_km,
                liters=liters,
                total_price_vat=total_price_vat,
                total_price_no_vat=_xlrd_decimal(sheet.cell(row_index, layout["total_price_no_vat"])),
                price_per_liter=_xlrd_decimal(sheet.cell(row_index, layout["price_per_liter"])),
                trip_km=trip_km,
                full_tank=_xlrd_bool(sheet.cell(row_index, layout["full_tank"])),
                average_consumption=_xlrd_decimal(sheet.cell(row_index, layout["average_consumption"])),
                source="excel",
                source_sheet=sheet.name,
                source_row=row_index + 1,
            )
            db.add(entry)
            imported_rows += 1
    db.commit()
    return {"imported_rows": imported_rows, "skipped_rows": skipped_rows}


def _find_fuel_header_row(sheet) -> int | None:
    for row_index in range(min(sheet.nrows, 20)):
        values = [_normalize_header(sheet.cell_value(row_index, column)) for column in range(sheet.ncols)]
        if "datum" in values and any(value.startswith("cerpaci") for value in values):
            return row_index
    return None


def _fuel_sheet_layout(sheet, header_row: int, sheet_name: str) -> dict:
    headers = [_normalize_header(sheet.cell_value(header_row, column)) for column in range(sheet.ncols)]
    date_col = headers.index("datum")
    has_time = date_col + 1 < len(headers) and headers[date_col + 1] == "cas"
    has_fuel_type = any(header.startswith("druh") for header in headers)
    offset = date_col + (2 if has_time else 1)
    if has_fuel_type:
        fuel_type_col = offset + 1
        odometer_col = offset + 2
        liters_col = offset + 3
        total_col = offset + 4
        no_vat_col = offset + 5
        price_col = offset + 6
        trip_col = offset + 7
        full_col = offset + 8
        average_col = offset + 9
    else:
        fuel_type_col = None
        odometer_col = offset + 1
        liters_col = offset + 2
        total_col = offset + 3
        no_vat_col = offset + 4
        price_col = offset + 5
        trip_col = offset + 6
        full_col = offset + 7
        average_col = offset + 8
    return {
        "date": date_col,
        "time": date_col + 1 if has_time else None,
        "station": offset,
        "fuel_type": fuel_type_col,
        "default_fuel_type": "LPG" if "LPG" in sheet_name.upper() else None,
        "odometer": odometer_col,
        "liters": liters_col,
        "total_price_vat": total_col,
        "total_price_no_vat": no_vat_col,
        "price_per_liter": price_col,
        "trip_km": trip_col,
        "full_tank": full_col,
        "average_consumption": average_col,
    }


def _normalize_header(value) -> str:
    return normalize_name(str(value)) if value is not None else ""


def _xlrd_text(cell) -> str | None:
    value = str(cell.value).strip()
    return value or None


def _xlrd_decimal(cell) -> Decimal | None:
    value = cell.value
    if value in (None, ""):
        return None
    try:
        if isinstance(value, str):
            value = value.replace(" ", "").replace("\xa0", "").replace(",", ".")
        return Decimal(str(value))
    except Exception:
        return None


def _xlrd_date(cell, datemode) -> date | None:
    import xlrd

    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode).date()
    if isinstance(cell.value, str):
        for date_format in ("%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(cell.value.strip(), date_format).date()
            except ValueError:
                pass
    return None


def _xlrd_time(cell, datemode) -> time | None:
    import xlrd

    if cell.value in (None, ""):
        return None
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode).time().replace(second=0, microsecond=0)
    if isinstance(cell.value, str):
        try:
            return datetime.strptime(cell.value.strip(), "%H:%M").time()
        except ValueError:
            return None
    return None


def _xlrd_bool(cell) -> bool | None:
    value = str(cell.value).strip().lower()
    if value in {"ano", "yes", "true", "1"}:
        return True
    if value in {"ne", "no", "false", "0"}:
        return False
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
    draft = {
        "spent_on": entry_date.isoformat(),
        "started_at": start.strftime("%H:%M"),
        "ended_at": end.strftime("%H:%M"),
        "duration_hours": str(duration),
        "category_code": resolved_category,
        "description": description,
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
