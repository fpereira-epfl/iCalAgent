from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any


@dataclass
class Event:
    """Normalized event structure used across scraping, parsing, and export."""

    title: str
    start: str
    end: str | None = None
    location: str | None = None
    description: str | None = None
    event_type: str | None = None
    source_url: str | None = None
    all_day: bool = False
    timezone: str | None = None
    event_id: str | None = None
    uid: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Event":
        title = str(raw.get("title", "")).strip()
        if not title:
            raise ValueError("Event title is required")

        start = str(raw.get("start", raw.get("start_datetime", ""))).strip()
        if not start:
            raise ValueError(f"Event start is required for '{title}'")

        end_value = raw.get("end", raw.get("end_datetime"))
        location = cls._clean_optional(raw.get("location"))
        source_url = cls._clean_optional(raw.get("source_url"))

        all_day = bool(raw.get("all_day", False))
        end = str(end_value).strip() if end_value else None
        start, end = cls._ensure_minimum_duration(start=start, end=end, all_day=all_day)

        event_id = cls._clean_optional(raw.get("id")) or cls._clean_optional(raw.get("event_id"))
        if not event_id:
            event_id = cls.build_event_id(
                title=title,
                start=start,
                end=end,
                location=location,
                source_url=source_url,
            )

        uid = cls._clean_optional(raw.get("uid")) or f"{event_id}@icalagent"

        return cls(
            title=title,
            start=start,
            end=end,
            location=location,
            description=cls._clean_optional(raw.get("description")),
            event_type=cls._clean_optional(raw.get("event_type")),
            source_url=source_url,
            all_day=all_day,
            timezone=cls._clean_optional(raw.get("timezone")),
            event_id=event_id,
            uid=uid,
        )

    @staticmethod
    def _clean_optional(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def to_dict(self) -> dict[str, Any]:
        event_id = self.event_id or self.build_event_id(
            title=self.title,
            start=self.start,
            end=self.end,
            location=self.location,
            source_url=self.source_url,
        )
        uid = self.uid or f"{event_id}@icalagent"
        return {
            "id": event_id,
            "title": self.title,
            "start": self.start,
            "end": self.end,
            "location": self.location,
            "description": self.description,
            "event_type": self.event_type,
            "source_url": self.source_url,
            "all_day": self.all_day,
            "timezone": self.timezone,
            "uid": uid,
        }

    def dtstamp(self) -> str:
        return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        text = value.strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00").replace(" ", "T")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            # Support common compact/non-ISO forms.
            for fmt in (
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%dT%H.%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d",
                "%Y%m%dT%H%M%S",
                "%Y%m%dT%H%M",
                "%Y%m%d",
            ):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _parse_time_only(value: str) -> time | None:
        if not value:
            return None
        text = value.strip()
        for fmt in ("%H:%M", "%H.%M", "%H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).time()
            except ValueError:
                continue
        return None

    @staticmethod
    def _format_datetime_like(original: str, dt: datetime) -> str:
        if "T" in original or " " in original:
            if ":" in original:
                return dt.strftime("%Y-%m-%dT%H:%M")
            return dt.strftime("%Y-%m-%dT%H%M%S")
        return dt.strftime("%Y-%m-%d")

    @classmethod
    def _ensure_minimum_duration(cls, start: str, end: str | None, all_day: bool) -> tuple[str, str | None]:
        if all_day:
            return start, end

        start_dt = cls._parse_datetime(start)
        start_t = cls._parse_time_only(start)
        end_t = cls._parse_time_only(end or "")
        if start_dt:
            min_end = start_dt + timedelta(hours=1)
            end_dt = cls._parse_datetime(end) if end else None
            if not end_dt or end_dt < min_end:
                return start, cls._format_datetime_like(start, min_end)
            return start, end

        # Fallback for time-only ranges like "20:00" -> "20:00".
        if start_t:
            start_clock = datetime.combine(datetime.today(), start_t)
            min_end_clock = start_clock + timedelta(hours=1)
            if not end_t:
                return start, min_end_clock.time().strftime("%H:%M")
            end_clock = datetime.combine(datetime.today(), end_t)
            if end_clock < min_end_clock:
                return start, min_end_clock.time().strftime("%H:%M")

        return start, end

    @staticmethod
    def _normalize_token(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip().lower()

    @classmethod
    def build_event_id(
        cls,
        title: str,
        start: str,
        end: str | None,
        location: str | None,
        source_url: str | None,
    ) -> str:
        title_slug = re.sub(r"[^a-z0-9]+", "-", cls._normalize_token(title)).strip("-")[:36] or "event"
        start_token = re.sub(r"[^0-9]", "", start)[:12] or "na"
        composite = "|".join(
            [
                cls._normalize_token(source_url),
                cls._normalize_token(title),
                cls._normalize_token(start),
                cls._normalize_token(end),
                cls._normalize_token(location),
            ]
        )
        digest = hashlib.sha1(composite.encode("utf-8")).hexdigest()[:12]
        return f"{start_token}-{title_slug}-{digest}"
