import csv
import re
import zipfile
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

WEIGHT_CSV_NAME_RE = re.compile(r"com\.samsung\.health\.weight\..*\.csv$", re.IGNORECASE)


def _extract_csv_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(file_path) as archive:
            member = next(
                (name for name in archive.namelist() if WEIGHT_CSV_NAME_RE.search(Path(name).name)),
                None,
            )
            if not member:
                raise ValueError("V exportu nebyl nalezen soubor s hmotnosti (com.samsung.health.weight.*.csv).")
            return archive.read(member).decode("utf-8-sig")
    if suffix == ".csv":
        return file_path.read_text(encoding="utf-8-sig")
    raise ValueError("Ocekavan je soubor .csv nebo .zip z exportu Samsung Health.")


def _parse_rows(csv_text: str) -> list[dict]:
    lines = csv_text.splitlines()
    if not lines:
        return []
    header_index = 1 if lines[0].startswith("com.samsung.health.weight") else 0
    reader = csv.DictReader(lines[header_index:])
    return [row for row in reader if row.get("start_time")]


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _parse_start_time(value: str) -> tuple[date, time] | None:
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date(), parsed.time().replace(microsecond=0)
        except ValueError:
            continue
    return None


def import_weight_export(db: Session, file_path: Path) -> dict:
    csv_text = _extract_csv_text(file_path)
    rows = _parse_rows(csv_text)

    existing_uuids = {
        value
        for value in db.scalars(
            select(models.WeightEntry.source_uuid).where(models.WeightEntry.source_uuid.is_not(None))
        ).all()
    }

    imported_rows = 0
    skipped_rows = 0
    for row in rows:
        source_uuid = (row.get("datauuid") or "").strip() or None
        weight_kg = _decimal_or_none(row.get("weight"))
        parsed_time = _parse_start_time(row.get("start_time", ""))
        if not weight_kg or not parsed_time:
            skipped_rows += 1
            continue
        if source_uuid and source_uuid in existing_uuids:
            skipped_rows += 1
            continue
        measured_on, measured_at = parsed_time
        db.add(
            models.WeightEntry(
                measured_on=measured_on,
                measured_at=measured_at,
                weight_kg=weight_kg,
                height_cm=_decimal_or_none(row.get("height")),
                body_fat_percent=_decimal_or_none(row.get("body_fat")),
                body_fat_mass_kg=_decimal_or_none(row.get("body_fat_mass")),
                muscle_mass_kg=_decimal_or_none(row.get("muscle_mass")),
                skeletal_muscle_mass_kg=_decimal_or_none(row.get("skeletal_muscle_mass")),
                basal_metabolic_rate=_decimal_or_none(row.get("basal_metabolic_rate")),
                total_body_water=_decimal_or_none(row.get("total_body_water")),
                vfa_level=_decimal_or_none(row.get("vfa_level")),
                note=(row.get("comment") or "").strip() or None,
                source="samsung_health",
                source_uuid=source_uuid,
            )
        )
        if source_uuid:
            existing_uuids.add(source_uuid)
        imported_rows += 1
        if imported_rows % 500 == 0:
            db.commit()
    db.commit()
    return {"imported_rows": imported_rows, "skipped_rows": skipped_rows}
