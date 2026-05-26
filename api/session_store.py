"""In-memory session store for temporary PDF files produced during comparison."""
import threading
from pathlib import Path

_lock = threading.Lock()
_sessions: dict[str, dict[str, Path | None]] = {}


def store_session(session_id: str, pdf_v1: Path | None, pdf_v2: Path | None) -> None:
    with _lock:
        _sessions[session_id] = {"pdf_v1": pdf_v1, "pdf_v2": pdf_v2}


def get_session(session_id: str) -> dict[str, Path | None] | None:
    with _lock:
        return _sessions.get(session_id)
