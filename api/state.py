"""Global mutable state shared across API routes.

Using a module-level dict avoids circular imports between main.py and routes.
"""
from typing import Any

embedder_state: dict[str, Any] = {"embedder": None}
