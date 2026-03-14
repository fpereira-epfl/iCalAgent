from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from icalagent.models.event import Event


def slugify(value: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return base or "agenda"


def stable_source_id(source_ref: str) -> str:
    clean = source_ref.strip()
    slug = slugify(clean)[:36] or "source"
    digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def save_raw_text(raw_text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(raw_text, encoding="utf-8")


def save_events_json(events: list[Event], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"events": [event.to_dict() for event in events]}
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def save_event_files_by_id(events: list[Event], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for event in events:
        event_payload = event.to_dict()
        event_id = event_payload["id"]
        json_path = output_dir / f"{event_id}.json"
        ics_path = output_dir / f"{event_id}.ics"

        json_path.write_text(json.dumps(event_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        export_events_to_ics([event], ics_path, calendar_name="iCalAgent Event")
        written.extend([json_path, ics_path])

    return written


def save_parsed_events_by_platform(events: list[Event], output_root: Path) -> dict[str, object]:
    json_dir = output_root / "json"
    ics_dir = output_root / "ics"
    json_dir.mkdir(parents=True, exist_ok=True)
    ics_dir.mkdir(parents=True, exist_ok=True)

    files_written = 0
    for event in events:
        event_payload = event.to_dict()
        event_id = event_payload["id"]

        json_path = json_dir / f"{event_id}.json"
        json_path.write_text(json.dumps(event_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        files_written += 1

        ics_path = ics_dir / f"{event_id}.ics"
        export_events_to_ics([event], ics_path, calendar_name="iCalAgent")
        files_written += 1

    return {
        "json_dir": json_dir,
        "ics_dir": ics_dir,
        "files_written": files_written,
    }


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _to_ics_datetime(value: str, all_day: bool) -> tuple[str, str]:
    clean = value.strip()
    if all_day:
        date = clean.replace("-", "")[:8]
        return "VALUE=DATE", date

    normalized = clean.replace("Z", "")
    normalized = normalized.replace("-", "").replace(":", "")
    normalized = normalized.replace(" ", "T")
    if "T" not in normalized and len(normalized) >= 8:
        normalized = f"{normalized[:8]}T000000"
    if "T" in normalized:
        date_part, time_part = normalized.split("T", 1)
    else:
        date_part, time_part = normalized[:8], normalized[8:]

    date_part = (date_part + "00000000")[:8]
    time_digits = "".join(ch for ch in time_part if ch.isdigit())
    if len(time_digits) >= 6:
        time_part = time_digits[:6]
    elif len(time_digits) == 4:
        time_part = f"{time_digits}00"
    elif len(time_digits) == 2:
        time_part = f"{time_digits}0000"
    else:
        time_part = "000000"

    normalized = f"{date_part}T{time_part}"
    return "", normalized


def _ensure_min_dtend(dtstart_value: str, dtend_value: str) -> str:
    try:
        start_dt = datetime.strptime(dtstart_value, "%Y%m%dT%H%M%S")
        end_dt = datetime.strptime(dtend_value, "%Y%m%dT%H%M%S")
    except ValueError:
        return dtend_value
    if end_dt <= start_dt:
        return (start_dt + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
    return dtend_value


def export_events_to_ics(events: list[Event], output_path: Path, calendar_name: str = "iCalAgent") -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//iCalAgent//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]

    for event in events:
        event_payload = event.to_dict()
        event_uid = event_payload.get("uid") or f"{event_payload['id']}@icalagent"

        dtstart_param, dtstart_value = _to_ics_datetime(event.start, event.all_day)
        dtend_line = None
        if event.end:
            dtend_param, dtend_value = _to_ics_datetime(event.end, event.all_day)
            if not event.all_day and not dtstart_param and not dtend_param:
                dtend_value = _ensure_min_dtend(dtstart_value, dtend_value)
            dtend_key = "DTEND" if not dtend_param else f"DTEND;{dtend_param}"
            dtend_line = f"{dtend_key}:{dtend_value}"

        dtstart_key = "DTSTART" if not dtstart_param else f"DTSTART;{dtstart_param}"

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event_uid}",
                f"DTSTAMP:{event.dtstamp()}",
                f"{dtstart_key}:{dtstart_value}",
                f"SUMMARY:{_ics_escape(event.title)}",
            ]
        )

        if dtend_line:
            lines.append(dtend_line)
        if event.location:
            lines.append(f"LOCATION:{_ics_escape(event.location)}")
        if event.description:
            lines.append(f"DESCRIPTION:{_ics_escape(event.description)}")
        if event.source_url:
            lines.append(f"URL:{_ics_escape(event.source_url)}")

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    output_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
