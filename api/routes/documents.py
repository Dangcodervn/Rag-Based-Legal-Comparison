"""GET /api/pdf/{session_id}/{version} — serve converted PDF files."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.session_store import get_session

router = APIRouter(tags=["documents"])


@router.get("/pdf/{session_id}/{version}")
async def get_pdf(session_id: str, version: str):
    if version not in ("v1", "v2"):
        raise HTTPException(status_code=400, detail="version must be 'v1' or 'v2'")

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    pdf_path = session.get(f"pdf_{version}")
    if not pdf_path or not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail="PDF unavailable — conversion may have failed for this document.",
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={pdf_path.name}"},
    )
