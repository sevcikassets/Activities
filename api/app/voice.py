import re
from datetime import date


TIME_RANGE_RE = re.compile(
    r"(?P<from>\d{1,2}[:.]\d{2}|\d{1,2})\s*(?:-|az|do)\s*(?P<to>\d{1,2}[:.]\d{2}|\d{1,2})",
    re.IGNORECASE,
)
TICKET_RE = re.compile(r"(?:ticket|tiket)\s*(?P<ticket>\d+)", re.IGNORECASE)


def normalize_time(value: str) -> str:
    text = value.replace(".", ":")
    if ":" not in text:
        text = f"{text}:00"
    hour, minute = text.split(":", 1)
    return f"{int(hour):02d}:{int(minute):02d}"


def parse_voice_text(text: str) -> tuple[dict, list[str]]:
    notes: list[str] = []
    draft: dict = {
        "spent_on": date.today().isoformat(),
        "description": text,
        "raw_text": text,
    }

    time_match = TIME_RANGE_RE.search(text)
    if time_match:
        draft["started_at"] = normalize_time(time_match.group("from"))
        draft["ended_at"] = normalize_time(time_match.group("to"))
    else:
        notes.append("Nepodarilo se jednoznacne rozpoznat cas od-do.")

    ticket_match = TICKET_RE.search(text)
    if ticket_match:
        draft["ticket_external_id"] = ticket_match.group("ticket")
    else:
        notes.append("Nepodarilo se rozpoznat cislo tiketu.")

    project_match = re.search(r"\b(?:pro|z)\s+(?P<project>[\w .+-]+)$", text, re.IGNORECASE)
    if project_match:
        draft["project_name"] = project_match.group("project").strip()
    else:
        notes.append("Projekt bude potreba potvrdit nebo vybrat rucne.")

    return draft, notes

