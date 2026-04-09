import time
import base64
import tempfile
from io import BytesIO
from typing import Optional

import httpx
from PIL import Image
from app.config import settings

try:
    from pyfingerprint.pyfingerprint import PyFingerprint
except Exception:  # pragma: no cover
    PyFingerprint = None


class FingerprintService:
    def _create_sensor(self):
        if PyFingerprint is None:
            raise RuntimeError(
                "pyfingerprint is not installed. Run: pip install pyfingerprint"
            )

        sensor = PyFingerprint(
            settings.fingerprint_serial_port,
            settings.fingerprint_baud_rate,
            settings.fingerprint_sensor_address,
            settings.fingerprint_sensor_password,
        )

        if not sensor.verifyPassword():
            raise RuntimeError("Fingerprint sensor password is invalid.")
        return sensor

    def _wait_for_finger(self, sensor, timeout_seconds: int) -> None:
        start = time.time()
        while not sensor.readImage():
            if time.time() - start > timeout_seconds:
                raise TimeoutError("Timeout waiting for fingerprint image.")
            time.sleep(0.1)

    def _capture_image_base64(self, sensor) -> str:
        with tempfile.NamedTemporaryFile(suffix=".bmp") as temp_bmp:
            sensor.downloadImage(temp_bmp.name)
            image = Image.open(temp_bmp.name)

            png_buffer = BytesIO()
            image.save(png_buffer, format="PNG")

        return base64.b64encode(png_buffer.getvalue()).decode("utf-8")

    def _post_event_to_wms(self, payload: dict) -> None:
        if not settings.send_events_to_wms:
            return

        endpoint = settings.wms_api_base_url.rstrip("/") + settings.wms_events_endpoint
        headers = {
            "X-Device-Key": settings.wms_device_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = httpx.post(endpoint, json=payload, headers=headers, timeout=10.0)
        response.raise_for_status()

    def enroll(self, include_image: bool = True) -> dict:
        sensor = self._create_sensor()

        self._wait_for_finger(sensor, settings.fingerprint_read_timeout_seconds)
        image_base64 = self._capture_image_base64(sensor) if include_image else None
        sensor.convertImage(0x01)
        result = sensor.searchTemplate()
        if result[0] >= 0:
            response = {
                "status": "already_exists",
                "position": result[0],
                "accuracy_score": result[1],
            }
            if image_base64:
                response["fingerprint_image_base64"] = image_base64
                response["fingerprint_image_mime"] = "image/png"
            return response

        time.sleep(2)
        self._wait_for_finger(sensor, settings.fingerprint_read_timeout_seconds)
        sensor.convertImage(0x02)

        if sensor.compareCharacteristics() == 0:
            raise RuntimeError("Fingerprints from first and second scan do not match.")

        sensor.createTemplate()
        position_number = sensor.storeTemplate()
        response = {"status": "enrolled", "position": position_number}
        if image_base64:
            response["fingerprint_image_base64"] = image_base64
            response["fingerprint_image_mime"] = "image/png"
        return response

    def search(self, include_image: bool = True, deposit_id: Optional[int] = None) -> dict:
        sensor = self._create_sensor()

        self._wait_for_finger(sensor, settings.fingerprint_read_timeout_seconds)
        image_base64 = self._capture_image_base64(sensor) if include_image else None
        sensor.convertImage(0x01)

        result = sensor.searchTemplate()
        position_number = result[0]
        accuracy_score = result[1]
        if position_number == -1:
            response = {
                "match": False,
                "position": -1,
                "accuracy_score": accuracy_score,
            }
            if image_base64:
                response["fingerprint_image_base64"] = image_base64
                response["fingerprint_image_mime"] = "image/png"
            self._post_event_to_wms(
                {
                    "device_code": settings.wms_device_id,
                    "event_type": "verify_failed",
                    "match_score": accuracy_score,
                    "deposit_id": deposit_id,
                    "fingerprint_image_base64": image_base64,
                    "fingerprint_image_mime": "image/png" if image_base64 else None,
                }
            )
            return response

        response = {"match": True, "position": position_number, "accuracy_score": accuracy_score}
        if image_base64:
            response["fingerprint_image_base64"] = image_base64
            response["fingerprint_image_mime"] = "image/png"

        self._post_event_to_wms(
            {
                "device_code": settings.wms_device_id,
                "event_type": "verify_success",
                "fingerprint_uid": str(position_number),
                "matched_user_id": None,
                "match_score": accuracy_score,
                "deposit_id": deposit_id,
                "fingerprint_image_base64": image_base64,
                "fingerprint_image_mime": "image/png" if image_base64 else None,
            }
        )
        return response

    def delete(self, position: int) -> dict:
        sensor = self._create_sensor()
        deleted = sensor.deleteTemplate(position)
        if not deleted:
            raise RuntimeError(f"Failed to delete template at position {position}.")
        return {"status": "deleted", "position": position}
