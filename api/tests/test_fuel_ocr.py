from decimal import Decimal

from app.fuel_ocr import (
    _parse_dashboard_km,
    _parse_date,
    _parse_liters,
    _parse_price_per_liter,
    _parse_receipt_text,
    _parse_station,
    _parse_time,
    _parse_total_price,
    _normalize_text,
)

OMV_RECEIPT_TEXT = """CS OMV 2067
Kromeriz
Hulinska 2253/22, Kromeriz
Tel: 608173000
STAHNETE SI APLIKACI
OMV MyStation
www.omv.cz/mystation
Datum:
28.08.2026 20:37:55
Pokladna c.: 1
Interni c.: dokladu.
PAN: XXXXXXXXXXXX2009X
On-line PIN:
AUTH:677930
TID:0223114B
TXID:261552
BATCH:012769
27101245 Natural 95 l
*1  Natural 95 l
58.220 l
x 42.90 CZK/l
Sazba spo. dane
12.8400
747.5448
Suma za celkem:
Celkem:
2497.60 CZK"""

TESLA_TRIP_COMPUTER_TEXT = """Trip computer
TM Trip Manual        TA Trip Auto
852.9 km               81.9 km
6.7 l/100km            2.4 l/100km
10:17 h                01:40 h
86 km/h                52 km/h
ODO: 96 214 km"""


def test_parse_receipt_text_extracts_all_fields():
    draft = _parse_receipt_text(OMV_RECEIPT_TEXT)
    assert draft["purchased_on"] == "2026-08-28"
    assert draft["purchased_at"] == "20:37"
    assert draft["station"] == "CS OMV 2067"
    assert draft["liters"] == "58.220"
    assert draft["price_per_liter"] == "42.90"
    assert draft["total_price_vat"] == "2497.60"
    assert draft["fuel_type"] == "Natural 95"


def test_parse_liters_prefers_decimal_quantity_over_octane_number():
    # "Natural 95 l" (the product name) appears before the real quantity;
    # the octane number must not be mistaken for the liters purchased.
    text = "Natural 95 l\n58.220 l"
    assert _parse_liters(text) == Decimal("58.220")


def test_parse_liters_falls_back_to_plain_integer():
    assert _parse_liters("40 l") == Decimal("40")


def test_parse_liters_reads_mnozstvi_keyword():
    assert _parse_liters("mnozstvi 35.5") == Decimal("35.5")


def test_parse_price_per_liter_accepts_plausible_range():
    assert _parse_price_per_liter("42.90 CZK/l") == Decimal("42.90")


def test_parse_price_per_liter_rejects_out_of_range_value():
    # A value like "5/l" or "250/l" is not a plausible CZK fuel price.
    assert _parse_price_per_liter("5 CZK/l") is None
    assert _parse_price_per_liter("250 CZK/l") is None


def test_parse_total_price_picks_celkem_amount():
    assert _parse_total_price(OMV_RECEIPT_TEXT) == Decimal("2497.60")


def test_parse_total_price_ignores_small_amounts():
    assert _parse_total_price("42.90 czk") is None


def test_parse_date_handles_dotted_format():
    assert _parse_date("Datum: 28.08.2026 20:37:55").isoformat() == "2026-08-28"


def test_parse_time_handles_seconds():
    assert _parse_time("28.08.2026 20:37:55") == "20:37"


def test_parse_station_matches_known_chain():
    assert _parse_station(OMV_RECEIPT_TEXT) == "CS OMV 2067"


def test_parse_station_falls_back_to_first_line():
    assert _parse_station("Neznama pumpa s.r.o.\nDalsi radek") == "Neznama pumpa s.r.o."


def test_parse_dashboard_km_handles_thousands_separator_space():
    km = _parse_dashboard_km(_normalize_text(TESLA_TRIP_COMPUTER_TEXT))
    assert km == Decimal("96214")


def test_parse_dashboard_km_ignores_trip_and_speed_readings():
    # Trip distance (852.9 km) and speed (86 km/h) readings on the same
    # screen must not be mistaken for the odometer total.
    text = _normalize_text("852.9 km\n86 km/h\nODO: 12345 km")
    assert _parse_dashboard_km(text) == Decimal("12345")


def test_parse_dashboard_km_handles_plain_digits():
    assert _parse_dashboard_km("stav 123456 km") == Decimal("123456")
