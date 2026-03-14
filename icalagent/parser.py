from __future__ import annotations

import json
import re
import time
from collections import Counter
from typing import Any, Callable

from icalagent.config import env_int
from icalagent.event_types import normalize_event_type
from icalagent.models.event import Event


SYSTEM_PROMPT = (
    "You extract calendar events from agenda text. "
    "Translate extracted human-readable fields to English. "
    "Keep names/acronyms unchanged when translation would be incorrect. "
    "If a URL appears in the text, include it in source_url for the relevant event(s). "
    "Return strict JSON only. Never include markdown."
)

DEFAULT_MAX_CHARS_TOTAL = 180_000
DEFAULT_MAX_CHARS_PER_CHUNK = 60_000
DEFAULT_MAX_CHUNKS = 3
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120


def build_prompt(raw_text: str, source_url: str, event_types: list[str]) -> str:
    schema = {
        "events": [
            {
                "title": "string",
                "start": "ISO-8601 datetime or date string",
                "end": "ISO-8601 datetime or date string or null",
                "location": "string or null",
                "description": "string or null",
                "event_type": f"one of {event_types}",
                "all_day": False,
                "timezone": "IANA timezone string or null",
                "source_url": source_url,
            }
        ]
    }

    return (
        "Parse the agenda text into calendar events. "
        "Include every event that can be inferred with reasonable confidence. "
        "If source text is not English, translate title, location, and description to English. "
        f"Use exactly one event_type from this allowed list: {', '.join(event_types)}. "
        "Prepend title exactly as [TYPE] Title using that allowed type. "
        "If one or more URLs are present in the agenda text, capture the most relevant one in source_url. "
        "If time is missing but date exists, still create the event as all_day=true. "
        "Keep datetime values faithful to the source and do not convert timezone unless explicit. "
        "Use null when fields are unknown.\n\n"
        f"Output schema example:\n{json.dumps(schema, indent=2)}\n\n"
        f"Source URL: {source_url}\n\n"
        "Agenda text:\n"
        f"{raw_text}"
    )


def _strip_type_prefix(title: str) -> tuple[str, str | None]:
    match = re.match(r"^\s*\[([^\]]+)\]\s*(.*)$", title)
    if not match:
        return title.strip(), None
    type_name = normalize_event_type(match.group(1))
    bare = match.group(2).strip()
    return bare or title.strip(), type_name


def _split_text_chunks(raw_text: str, max_chars: int) -> list[str]:
    text = raw_text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in text.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars:
            chunks.append("\n".join(current).strip())
            current = []
            current_len = 0
        if line_len > max_chars:
            start = 0
            while start < len(line):
                end = start + max_chars
                part = line[start:end]
                if part.strip():
                    chunks.append(part.strip())
                start = end
            continue
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _score_line(line: str) -> int:
    score = 0
    if re.search(r"\b\d{1,2}[:.]\d{2}\b", line):
        score += 3
    if re.search(r"\b\d{1,2}[./-]\d{1,2}([./-]\d{2,4})?\b", line):
        score += 3
    if re.search(r"\b(20\d{2}|19\d{2})\b", line):
        score += 2
    if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)\b", line, flags=re.IGNORECASE):
        score += 2
    if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", line, flags=re.IGNORECASE):
        score += 2
    if len(line) > 180:
        score += 1
    return score


def _prepare_text_for_gpt(raw_text: str, max_total_chars: int, trace: Callable[[str], None] | None) -> str:
    text = raw_text.strip()
    if len(text) <= max_total_chars:
        return text

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text[:max_total_chars]

    scored = sorted(lines, key=_score_line, reverse=True)
    selected: list[str] = []
    total = 0

    for line in scored:
        line_len = len(line) + 1
        if total + line_len > max_total_chars:
            continue
        selected.append(line)
        total += line_len
        if total >= max_total_chars:
            break

    # Keep stable order from source.
    selected_counter = Counter(selected)
    ordered: list[str] = []
    for line in lines:
        if selected_counter[line] > 0:
            ordered.append(line)
            selected_counter[line] -= 1
    prepared = "\n".join(ordered).strip()
    if not prepared:
        prepared = text[:max_total_chars]

    if trace:
        trace(
            f"Input trimmed from {len(text)} to {len(prepared)} chars before GPT "
            f"(signal-focused selection, cap={max_total_chars})."
        )
    return prepared


def parse_events_with_gpt(
    raw_text: str,
    source_url: str,
    model: str,
    event_types: list[str],
    forced_event_type: str | None = None,
    trace: Callable[[str], None] | None = None,
) -> list[Event]:
    from icalagent.clients.gptclient import GPTConnector

    max_total_chars = env_int("ICALAGENT_GPT_MAX_TOTAL_CHARS", DEFAULT_MAX_CHARS_TOTAL)
    max_chars_per_chunk = env_int("ICALAGENT_GPT_MAX_CHARS_PER_CHUNK", DEFAULT_MAX_CHARS_PER_CHUNK)
    max_chunks = env_int("ICALAGENT_GPT_MAX_CHUNKS", DEFAULT_MAX_CHUNKS)
    request_timeout_seconds = env_int("ICALAGENT_OPENAI_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS)

    prepared_text = _prepare_text_for_gpt(raw_text=raw_text, max_total_chars=max_total_chars, trace=trace)

    connector = GPTConnector(model=model)
    chunks = _split_text_chunks(raw_text=prepared_text, max_chars=max_chars_per_chunk)
    if len(chunks) > max_chunks:
        if trace:
            trace(f"Chunk count capped: using first {max_chunks} of {len(chunks)} chunk(s).")
        chunks = chunks[:max_chunks]
    if not chunks:
        return []

    if trace:
        trace(f"Preparing {len(chunks)} GPT request chunk(s) from {len(prepared_text)} characters.")

    events_raw_all: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks, start=1):
        if trace:
            trace(f"Sending chunk {idx}/{len(chunks)} to GPT (size={len(chunk)} chars).")
        prompt = build_prompt(raw_text=chunk, source_url=source_url, event_types=event_types)
        started = time.time()
        payload = connector.send_prompt(
            prompt=prompt,
            system=SYSTEM_PROMPT,
            timeout_seconds=request_timeout_seconds,
        )
        if trace:
            trace(f"Chunk {idx}/{len(chunks)} completed in {time.time() - started:.1f}s.")

        events_raw: Any = payload.get("events", []) if isinstance(payload, dict) else []
        if not isinstance(events_raw, list):
            raise ValueError("Model output does not contain a valid 'events' list")
        events_raw_all.extend(item for item in events_raw if isinstance(item, dict))

    events: list[Event] = []
    allowed_types = {normalize_event_type(t) for t in event_types}
    fallback_type = "OTHER" if "OTHER" in allowed_types else normalize_event_type(event_types[0])
    forced_type = normalize_event_type(forced_event_type) if forced_event_type else None
    if forced_type and forced_type not in allowed_types:
        forced_type = None
    seen_event_ids: set[str] = set()
    for item in events_raw_all:
        raw_title = str(item.get("title", "")).strip()
        bare_title, prefix_type = _strip_type_prefix(raw_title)
        raw_type = normalize_event_type(str(item.get("event_type", "")).strip())
        if forced_type:
            event_type = forced_type
        else:
            event_type = raw_type if raw_type in allowed_types else prefix_type
            if event_type not in allowed_types:
                event_type = fallback_type
        item["event_type"] = event_type
        item["title"] = f"[{event_type}] {bare_title or 'Untitled Event'}"

        # Ensure provenance is always preserved when a source reference exists.
        if not str(item.get("source_url", "")).strip():
            item["source_url"] = source_url
        try:
            event = Event.from_dict(item)
        except ValueError:
            continue
        event_id = event.to_dict()["id"]
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(event_id)
        events.append(event)

    return events
