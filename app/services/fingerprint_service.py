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

    def _build_wms_event_payload(self, **fields) -> dict:
        return {key: value for key, value in fields.items() if value is not None}

    def _post_event_to_wms(self, payload: dict) -> Optional[str]:
        if not settings.send_events_to_wms:
            return None

        endpoint = settings.wms_events_url
        headers = {
            "X-Device-Key": settings.wms_device_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            response = httpx.post(endpoint, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            return (
                f"Conexiune refuzata la {endpoint}. "
                "Verifica portul din WMS_API_BASE_URL "
                "(ex: :8000 pentru php artisan serve). "
                f"Detalii: {exc}"
            )
        except httpx.RequestError as exc:
            return f"Nu s-a putut contacta WMS la {endpoint}: {exc}"
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or exc.response.reason_phrase
            return (
                f"WMS a respins evenimentul ({exc.response.status_code}) "
                f"la {endpoint}: {detail}"
            )

        return None

    def _attach_wms_status(self, response: dict, wms_error: Optional[str]) -> dict:
        if wms_error:
            response["wms_event_sent"] = False
            response["wms_event_error"] = wms_error
        elif settings.send_events_to_wms:
            response["wms_event_sent"] = True
        return response

    def enroll_first_scan(self, sensor, include_image: bool = True) -> dict:
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

        response = {"status": "first_scan_done"}
        if image_base64:
            response["fingerprint_image_base64"] = image_base64
            response["fingerprint_image_mime"] = "image/png"
        return response

    def enroll_second_scan(
        self,
        sensor,
        include_image: bool = True,
        image_base64: Optional[str] = None,
    ) -> dict:
        time.sleep(2)
        self._wait_for_finger(sensor, settings.fingerprint_read_timeout_seconds)
        if include_image:
            image_base64 = self._capture_image_base64(sensor)
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

    def enroll_with_sensor(self, sensor, include_image: bool = True) -> dict:
        first_result = self.enroll_first_scan(sensor, include_image=include_image)
        if first_result["status"] == "already_exists":
            return first_result

        return self.enroll_second_scan(
            sensor,
            include_image=include_image,
            image_base64=first_result.get("fingerprint_image_base64"),
        )

    def enroll(self, include_image: bool = True) -> dict:
        sensor = self._create_sensor()
        return self.enroll_with_sensor(sensor, include_image=include_image)

    def create_sensor(self):
        return self._create_sensor()

    def search_with_sensor(
        self,
        sensor,
        include_image: bool = True,
        deposit_id: Optional[int] = None,
    ) -> dict:
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
            wms_error = self._post_event_to_wms(
                self._build_wms_event_payload(
                    device_code=settings.wms_device_id,
                    event_type="verify_failed",
                    match_score=accuracy_score,
                    deposit_id=deposit_id,
                    fingerprint_image_base64=image_base64,
                    fingerprint_image_mime="image/png" if image_base64 else None,
                )
            )
            return self._attach_wms_status(response, wms_error)

        response = {"match": True, "position": position_number, "accuracy_score": accuracy_score}
        if image_base64:
            response["fingerprint_image_base64"] = image_base64
            response["fingerprint_image_mime"] = "image/png"

        wms_error = self._post_event_to_wms(
            self._build_wms_event_payload(
                device_code=settings.wms_device_id,
                event_type="verify_success",
                fingerprint_uid=str(position_number),
                match_score=accuracy_score,
                deposit_id=deposit_id,
                fingerprint_image_base64=image_base64,
                fingerprint_image_mime="image/png" if image_base64 else None,
            )
        )
        return self._attach_wms_status(response, wms_error)

    def search(self, include_image: bool = True, deposit_id: Optional[int] = None) -> dict:
        sensor = self._create_sensor()
        return self.search_with_sensor(
            sensor,
            include_image=include_image,
            deposit_id=deposit_id,
        )

    def delete(self, position: int) -> dict:
        sensor = self._create_sensor()
        deleted = sensor.deleteTemplate(position)
        if not deleted:
            raise RuntimeError(f"Failed to delete template at position {position}.")
        return {"status": "deleted", "position": position}
