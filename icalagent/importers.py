from __future__ import annotations

import json
from pathlib import Path

from icalagent.exporters import export_events_to_ics
from icalagent.models.event import Event


TARGETS = {"ics"}


def load_events_json(input_path: Path) -> list[Event]:
    if not input_path.exists():
        raise FileNotFoundError(f"Events JSON file not found: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    events_raw: list[dict]
    if isinstance(payload, dict) and "events" in payload:
        candidate = payload.get("events", [])
        events_raw = candidate if isinstance(candidate, list) else []
    elif isinstance(payload, dict):
        events_raw = [payload]
    else:
        events_raw = []

    events: list[Event] = []
    for item in events_raw:
        if isinstance(item, dict):
            events.append(Event.from_dict(item))
    return events


def select_events(events: list[Event], indices: list[int] | None, contains: str | None) -> list[Event]:
    selected = events

    if indices:
        valid_indexes = {index for index in indices if 1 <= index <= len(events)}
        selected = [event for idx, event in enumerate(events, start=1) if idx in valid_indexes]

    if contains:
        needle = contains.lower().strip()
        selected = [
            event
            for event in selected
            if needle in event.title.lower()
            or (event.description and needle in event.description.lower())
            or (event.location and needle in event.location.lower())
        ]

    return selected


def export_selected_for_targets(events: list[Event], output_dir: Path, basename: str, target: str) -> list[Path]:
    if target not in TARGETS:
        raise ValueError(f"Invalid target: {target}. Choose from: {', '.join(sorted(TARGETS))}")

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    if target == "ics":
        ics_path = output_dir / f"{basename}.ics"
        export_events_to_ics(events, ics_path, calendar_name="iCalAgent")
        written.append(ics_path)

    return written
