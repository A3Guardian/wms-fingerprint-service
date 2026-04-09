from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.services.fingerprint_service import FingerprintService

router = APIRouter()
fingerprint_service = FingerprintService()


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


@router.delete("/delete")
def delete_template(payload: DeleteTemplatePayload) -> dict:
    try:
        return fingerprint_service.delete(payload.position)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
