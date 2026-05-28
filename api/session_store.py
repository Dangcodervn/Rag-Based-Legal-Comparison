"""In-memory session store for temporary DOCX files produced during comparison."""
import threading
from pathlib import Path

_lock = threading.Lock()
_sessions: dict[str, dict[str, Path | None]] = {}


def store_session(session_id: str, docx_v1: Path | None, docx_v2: Path | None) -> None:
    with _lock:
        _sessions[session_id] = {"docx_v1": docx_v1, "docx_v2": docx_v2}


def get_session(session_id: str) -> dict[str, Path | None] | None:
    with _lock:
        return _sessions.get(session_id)
