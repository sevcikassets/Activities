from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re


class FuelOcrUnavailable(RuntimeError):
    pass


def parse_fuel_photos(receipt_bytes: bytes | None, dashboard_bytes: bytes | None) -> dict:
    texts = []
    notes = []
    if receipt_bytes:
        receipt_text = _detect_text(receipt_bytes)
        texts.append(receipt_text)
        notes.append("Uctenka byla rozpoznana.")
    if dashboard_bytes:
        dashboard_text = _detect_text(dashboard_bytes)
        texts.append(dashboard_text)
        notes.append("Palubni deska byla rozpoznana.")
    text = "\n".join(texts)
    draft = _parse_receipt_text(text)
    dashboard_km = _parse_dashboard_km(text)
    if dashboard_km is not None:
        draft["odometer_km"] = str(dashboard_km)
    if not draft:
        notes.append("Z fotek se nepodarilo spolehlive vycist hodnoty.")
    return {"draft": draft, "confidence_notes": notes, "raw_text": text}


def _detect_text(image_bytes: bytes) -> str:
    try:
        import boto3
    except ImportError as exc:
        raise FuelOcrUnavailable("OCR neni nainstalovane. Doplňte balicek boto3.") from exc
    try:
        client = boto3.client("textract")
        response = client.detect_document_text(Document={"Bytes": image_bytes})
    except Exception as exc:
        raise FuelOcrUnavailable("OCR neni dostupne. Zkontrolujte AWS credentials nebo instance role pro Textract.") from exc
    lines = [
        block.get("Text", "")
        for block in response.get("Blocks", [])
        if block.get("BlockType") == "LINE" and block.get("Text")
    ]
    return "\n".join(lines)


def _parse_receipt_text(text: str) -> dict:
    compact = _normalize_text(text)
    draft: dict[str, str] = {}
    parsed_date = _parse_date(compact)
    if parsed_date:
        draft["purchased_on"] = parsed_date.isoformat()
    parsed_time = _parse_time(compact)
    if parsed_time:
        draft["purchased_at"] = parsed_time
    station = _parse_station(text)
    if station:
        draft["station"] = station
    liters = _parse_liters(compact)
    if liters is not None:
        draft["liters"] = str(liters)
    price_per_liter = _parse_price_per_liter(compact)
    if price_per_liter is not None:
        draft["price_per_liter"] = str(price_per_liter)
    total = _parse_total_price(compact)
    if total is not None:
        draft["total_price_vat"] = str(total)
    if "nafta" in compact.lower() or "diesel" in compact.lower():
        draft["fuel_type"] = "Nafta"
    elif "natural" in compact.lower() or "benzin" in compact.lower() or "benzín" in compact.lower():
        draft["fuel_type"] = "Natural 95"
    elif "lpg" in compact.lower():
        draft["fuel_type"] = "LPG"
    odometer = _parse_dashboard_km(compact)
    if odometer is not None:
        draft["odometer_km"] = str(odometer)
    return draft


def _normalize_text(text: str) -> str:
    return text.replace("\xa0", " ").replace(",", ".")


def _parse_date(text: str) -> date | None:
    match = re.search(r"\b(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{2,4})\b", text)
    if not match:
        return None
    day, month, year = match.groups()
    year_number = int(year)
    if year_number < 100:
        year_number += 2000
    try:
        return date(year_number, int(month), int(day))
    except ValueError:
        return None


def _parse_time(text: str) -> str | None:
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b", text)
    if not match:
        return None
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _parse_station(text: str) -> str | None:
    for line in text.splitlines()[:8]:
        cleaned = " ".join(line.strip().split())
        if len(cleaned) < 3:
            continue
        lowered = cleaned.lower()
        if any(name in lowered for name in ["shell", "mol", "benzina", "orlen", "omv", "eurooil", "tank ono", "ono"]):
            return cleaned[:80]
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first_line[:80] or None


def _parse_liters(text: str) -> Decimal | None:
    patterns = [
        # Decimal quantities first: fuel pumps always print fractional liters
        # (e.g. "58.220 l"), which keeps this from matching an octane number
        # like "Natural 95 l" printed earlier on the receipt.
        r"(\d+\.\d+)\s*l(?:itru|itry|itr|\.|\b)",
        r"mnozstvi\s*(\d+(?:\.\d+)?)",
        r"(\d+)\s*l(?:itru|itry|itr|\.|\b)",
    ]
    return _first_decimal(text, patterns)


def _parse_price_per_liter(text: str) -> Decimal | None:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:kc|czk)?\s*/\s*l",
        r"cena\s*(?:mj|za\s*l|/l)?\s*(\d+(?:\.\d+)?)",
    ]
    value = _first_decimal(text, patterns)
    if value is not None and Decimal("10") <= value <= Decimal("100"):
        return value
    return None


def _parse_total_price(text: str) -> Decimal | None:
    candidates = [
        _first_decimal(text, [r"(?:celkem|castka|k uhrade|úhrade|uhrazeno)\D{0,16}(\d+(?:\.\d+)?)"]),
        _first_decimal(text, [r"(\d+(?:\.\d+)?)\s*(?:kc|czk)\b"]),
    ]
    values = [value for value in candidates if value is not None and value >= Decimal("100")]
    return max(values) if values else None


_KM_NUMBER = r"(?:\d{1,3}(?:\s\d{3})+|\d{4,7})"


def _parse_dashboard_km(text: str) -> Decimal | None:
    # Odometer readings are often printed with a thousands separator space,
    # e.g. dashboard trip computers showing "ODO: 96 214 km".
    patterns = [
        rf"({_KM_NUMBER})\s*km\b",
        rf"\bodo(?:meter)?\D{{0,10}}({_KM_NUMBER})\b",
        rf"\bstav\D{{0,10}}({_KM_NUMBER})\b",
    ]
    return _first_decimal(text, patterns)


def _first_decimal(text: str, patterns: list[str]) -> Decimal | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return Decimal(match.group(1).replace(" ", "").replace(",", "."))
            except Exception:
                return None
    return None
