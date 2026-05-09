import re
import time

_PROGRESS_RE = re.compile(
    r"\[download\]\s+([\d.]+)%\s+of\s+\S+\s+at\s+(\S+)"
)

_COMPLETE_RE = re.compile(
    r"\[download\]\s+(100(?:\.0)?)%\s+of"
)


def parse_ytdlp_progress(line: str) -> dict | None:
    m = _PROGRESS_RE.search(line)
    if m:
        return {"percent": float(m.group(1)), "speed": m.group(2)}
    m = _COMPLETE_RE.search(line)
    if m:
        return {"percent": 100.0, "speed": ""}
    return None


def format_progress_bar(percent: float, speed: str, width: int = 12) -> str:
    filled = int(width * percent / 100)
    bar = "\u2501" * filled + "\u2591" * (width - filled)
    pct = f"{percent:.0f}%"
    parts = [f"\u2b07\ufe0f {pct} {bar}"]
    if speed:
        parts.append(speed)
    return " ".join(parts)


class ProgressThrottle:
    def __init__(self, interval: float = 3.0):
        self._interval = interval
        self._last_update = 0.0

    def should_update(self) -> bool:
        now = time.monotonic()
        if now - self._last_update >= self._interval:
            self._last_update = now
            return True
        return False
