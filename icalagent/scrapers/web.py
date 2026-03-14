from __future__ import annotations

from bs4 import BeautifulSoup
import requests


def scrape_agenda_text(url: str, timeout: int = 25, max_chars: int = 3_000_000) -> str:
    """Scrape text while preserving as much agenda detail as possible."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    pieces: list[str] = []

    if soup.title and soup.title.string:
        pieces.append(f"TITLE: {soup.title.string.strip()}")

    for element in soup.find_all([
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "li",
        "td",
        "th",
        "time",
    ]):
        text = " ".join(element.get_text(" ", strip=True).split())
        if text and len(text) > 2:
            pieces.append(text)

    # Preserve a broad text body fallback only when structured extraction is sparse.
    body_text = "\n".join(soup.stripped_strings)
    if body_text and len(pieces) < 10:
        pieces.append("FULL_TEXT:")
        pieces.append(body_text)

    # Deduplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for item in pieces:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    text = "\n".join(deduped)
    if len(text) > max_chars:
        text = text[:max_chars]
    return text
