from __future__ import annotations

import json
from pathlib import Path


def load_agenda_urls(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Agenda file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        urls = data.get("urls", [])
    else:
        urls = data

    if not isinstance(urls, list):
        raise ValueError("Agenda file must be a JSON list or {\"urls\": [...]} object")

    cleaned = [str(url).strip() for url in urls if str(url).strip()]
    return cleaned
