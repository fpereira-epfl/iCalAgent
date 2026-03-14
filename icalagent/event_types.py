from __future__ import annotations

from pathlib import Path


def normalize_event_type(value: str) -> str:
    return " ".join(value.strip().upper().split())


def load_event_types(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Event types file not found: {path}")

    types: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        normalized = normalize_event_type(line)
        if normalized and normalized not in types:
            types.append(normalized)

    if not types:
        raise ValueError(f"No event types found in: {path}")

    return types
