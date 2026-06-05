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
        poll_interval = settings.fingerprint_poll_interval_seconds
        while not sensor.readImage():
            if time.time() - start > timeout_seconds:
                raise TimeoutError("Timeout waiting for fingerprint image.")
            time.sleep(poll_interval)

    def _normalize_match_score(self, score: int) -> Optional[int]:
        if score < 0:
            return None
        return min(int(score), 65535)

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
        include_image: Optional[bool] = None,
        deposit_id: Optional[int] = None,
    ) -> dict:
        capture_image = (
            settings.search_include_image if include_image is None else include_image
        )

        self._wait_for_finger(sensor, settings.fingerprint_read_timeout_seconds)
        sensor.convertImage(0x01)

        result = sensor.searchTemplate()
        position_number = result[0]
        accuracy_score = result[1]
        wms_match_score = self._normalize_match_score(accuracy_score)

        image_base64 = None
        if capture_image:
            image_base64 = self._capture_image_base64(sensor)

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
                    match_score=wms_match_score,
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
                match_score=wms_match_score,
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

    def _get_storage_capacity(self, sensor) -> int:
        try:
            return int(sensor.getStorageCapacity())
        except Exception:
            return 256

    def _index_pages_for_capacity(self, capacity: int) -> range:
        last_position = max(0, capacity - 1)
        max_page = min(3, last_position // 256)
        return range(max_page + 1)

    def _list_occupied_positions_from_index(self, sensor, capacity: int) -> list[int]:
        positions: list[int] = []
        for page in self._index_pages_for_capacity(capacity):
            usage_flags = sensor.getTemplateIndex(page)
            for offset, is_used in enumerate(usage_flags):
                position = page * 256 + offset
                if position >= capacity:
                    continue
                if is_used:
                    positions.append(position)
        return positions

    def _list_occupied_positions_by_probe(self, sensor, capacity: int) -> list[int]:
        positions: list[int] = []
        for position in range(capacity):
            try:
                if sensor.loadTemplate(position):
                    positions.append(position)
            except Exception:
                continue
        return positions

    def _list_occupied_positions(self, sensor, capacity: int) -> tuple[list[int], str]:
        try:
            return self._list_occupied_positions_from_index(sensor, capacity), "index"
        except Exception:
            return self._list_occupied_positions_by_probe(sensor, capacity), "probe"

    def list_templates(self) -> dict:
        sensor = self._create_sensor()
        count = sensor.getTemplateCount()
        capacity = self._get_storage_capacity(sensor)
        positions, positions_source = self._list_occupied_positions(sensor, capacity)
        return {
            "template_count": count,
            "storage_capacity": capacity,
            "positions": positions,
            "positions_source": positions_source,
        }

    def delete(self, position: int) -> dict:
        sensor = self._create_sensor()
        deleted = sensor.deleteTemplate(position)
        if not deleted:
            raise RuntimeError(f"Failed to delete template at position {position}.")
        return {"status": "deleted", "position": position}

    def clear_all_templates(self) -> dict:
        sensor = self._create_sensor()
        previous_count = sensor.getTemplateCount()
        cleared = sensor.clearDatabase()
        if not cleared:
            raise RuntimeError("Failed to clear fingerprint database on sensor.")
        return {
            "status": "cleared",
            "deleted_count": previous_count,
            "template_count": sensor.getTemplateCount(),
        }
