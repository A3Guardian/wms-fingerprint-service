from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.services.enroll_session import EnrollSessionManager
from app.services.fingerprint_service import FingerprintService

router = APIRouter()
fingerprint_service = FingerprintService()
enroll_session_manager = EnrollSessionManager()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


class DeleteTemplatePayload(BaseModel):
    position: int = Field(ge=0)


class ScanPayload(BaseModel):
    include_image: bool = True
    deposit_id: Optional[int] = Field(default=None, ge=1)


@router.post("/enroll")
def enroll(payload: ScanPayload) -> dict:
    try:
        return fingerprint_service.enroll(include_image=payload.include_image)
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class EnrollSessionPayload(BaseModel):
    include_image: bool = True


@router.post("/enroll/session")
def start_enroll_session(payload: EnrollSessionPayload) -> dict:
    try:
        return enroll_session_manager.start(include_image=payload.include_image)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/enroll/session/{session_id}/first-scan")
def enroll_first_scan(session_id: str) -> dict:
    try:
        return enroll_session_manager.first_scan(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/enroll/session/{session_id}/second-scan")
def enroll_second_scan(session_id: str) -> dict:
    try:
        return enroll_session_manager.second_scan(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/enroll/session/{session_id}")
def cancel_enroll_session(session_id: str) -> dict:
    return enroll_session_manager.cancel(session_id)


@router.post("/search")
def search(payload: ScanPayload) -> dict:
    try:
        return fingerprint_service.search(
            include_image=payload.include_image,
            deposit_id=payload.deposit_id,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates")
def list_templates() -> dict:
    try:
        return fingerprint_service.list_templates()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/delete")
def delete_template(payload: DeleteTemplatePayload) -> dict:
    try:
        return fingerprint_service.delete(payload.position)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/templates")
def clear_templates() -> dict:
    try:
        return fingerprint_service.clear_all_templates()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
