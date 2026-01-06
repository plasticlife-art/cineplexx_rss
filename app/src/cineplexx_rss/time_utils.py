from __future__ import annotations

from math import floor


def format_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    mins = total_seconds // 60
    secs = total_seconds % 60

    parts = []
    if mins:
        parts.append(f"{mins}m")
    if secs or mins:
        parts.append(f"{secs}s")
    if ms and not mins:
        parts.append(f"{ms}ms")
    elif ms:
        parts.append(f"{ms}ms")
    if not parts:
        return "0ms"
    return " ".join(parts)
