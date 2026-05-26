"""GET /api/health — check embedding model and Ollama readiness."""
import httpx
from fastapi import APIRouter

from configs.defaults import OLLAMA_BASE_URL
from api.state import embedder_state
from api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    embedder_ready = embedder_state.get("embedder") is not None

    ollama_ready = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_ready = resp.status_code == 200
    except Exception:
        pass

    return HealthResponse(
        embedder="ready" if embedder_ready else "loading",
        ollama="ready" if ollama_ready else "error",
    )
