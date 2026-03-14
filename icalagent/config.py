from __future__ import annotations

import os

def load_env() -> None:
    """Load environment variables from .env if present."""
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return
    load_dotenv()


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    clean = value.strip()
    return clean if clean else default


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default

