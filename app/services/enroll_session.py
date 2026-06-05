import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.services.fingerprint_service import FingerprintService

ProgressCallback = Callable[[str], None]


@dataclass
class EnrollSession:
    session_id: str
    sensor: object
    include_image: bool = True
    stage: str = "ready"
    image_base64: Optional[str] = None
    created_at: float = field(default_factory=time.time)


class EnrollSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, EnrollSession] = {}
        self._lock = threading.Lock()
        self._service = FingerprintService()
        self._ttl_seconds = 300

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.created_at > self._ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    def start(self, include_image: bool = True) -> dict:
        with self._lock:
            self._cleanup_expired()
            sensor = self._service.create_sensor()
            session_id = str(uuid.uuid4())
            self._sessions[session_id] = EnrollSession(
                session_id=session_id,
                sensor=sensor,
                include_image=include_image,
            )
            return {
                "session_id": session_id,
                "status": "ready",
                "message": "Astept prima scanare.",
            }

    def _get_session(self, session_id: str) -> EnrollSession:
        self._cleanup_expired()
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Enrollment session '{session_id}' not found or expired.")
        return session

    def first_scan(self, session_id: str, on_progress: Optional[ProgressCallback] = None) -> dict:
        with self._lock:
            session = self._get_session(session_id)
            if session.stage != "ready":
                raise RuntimeError("Prima scanare a fost deja efectuata.")

        if on_progress:
            on_progress("Astept prima scanare...")
        result = self._service.enroll_first_scan(
            session.sensor,
            include_image=session.include_image,
        )

        with self._lock:
            session = self._get_session(session_id)
            if result.get("fingerprint_image_base64"):
                session.image_base64 = result["fingerprint_image_base64"]

            if result["status"] == "already_exists":
                self._sessions.pop(session_id, None)
                return result

            session.stage = "first_done"
            return result

    def second_scan(self, session_id: str, on_progress: Optional[ProgressCallback] = None) -> dict:
        with self._lock:
            session = self._get_session(session_id)
            if session.stage != "first_done":
                raise RuntimeError("Finalizeaza mai intai prima scanare.")

        if on_progress:
            on_progress("Rescanati aceeasi amprenta...")
        result = self._service.enroll_second_scan(
            session.sensor,
            include_image=session.include_image,
            image_base64=session.image_base64,
        )

        with self._lock:
            self._sessions.pop(session_id, None)

        return result

    def cancel(self, session_id: str) -> dict:
        with self._lock:
            removed = self._sessions.pop(session_id, None) is not None
        return {"status": "cancelled" if removed else "not_found", "session_id": session_id}
