import argparse
import sys
import time
from datetime import datetime
from typing import Optional

import httpx

from app.config import settings
from app.services.fingerprint_service import FingerprintService


def _log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _log_wms_config() -> None:
    if not settings.send_events_to_wms:
        _log("Trimitere evenimente WMS: dezactivata (SEND_EVENTS_TO_WMS=false).")
        return

    _log("Trimitere evenimente WMS: activa.")
    _log(f"  URL: {settings.wms_events_url}")
    _log(f"  Dispozitiv: {settings.wms_device_id}")


def run_check_wms() -> int:
    base_url = settings.wms_api_base_url.rstrip("/")
    events_url = settings.wms_events_url

    _log("Verificare conectivitate WMS...")
    _log(f"  WMS_API_BASE_URL: {base_url}")
    _log(f"  Endpoint evenimente: {events_url}")
    _log(f"  Dispozitiv: {settings.wms_device_id}")

    try:
        response = httpx.get(base_url, timeout=5.0, follow_redirects=True)
        _log(f"GET {base_url} -> HTTP {response.status_code}")
    except httpx.ConnectError as exc:
        _log(
            "GET esuat: conexiune refuzata. "
            "Adauga portul corect in WMS_API_BASE_URL "
            "(ex: http://192.168.68.22:8000)."
        )
        _log(f"  Detalii: {exc}")
        return 1
    except httpx.RequestError as exc:
        _log(f"GET esuat: {exc}")
        return 1

    headers = {
        "X-Device-Key": settings.wms_device_secret,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    probe_payload = {
        "device_code": settings.wms_device_id,
        "event_type": "connectivity_probe",
        "match_score": 0,
    }

    try:
        response = httpx.post(
            events_url,
            json=probe_payload,
            headers=headers,
            timeout=10.0,
        )
        _log(f"POST {events_url} -> HTTP {response.status_code}")
        if response.status_code >= 400:
            body = response.text.strip()
            if body:
                _log(f"  Raspuns: {body[:500]}")
            if response.status_code == 403:
                _log(
                    "  Verifica in WMS: code dispozitiv = WMS_DEVICE_ID "
                    "si api_key = WMS_DEVICE_SECRET."
                )
            return 1
    except httpx.ConnectError as exc:
        _log(
            "POST esuat: conexiune refuzata la endpointul de evenimente. "
            "Portul din WMS_API_BASE_URL este probabil gresit."
        )
        _log(f"  Detalii: {exc}")
        return 1
    except httpx.RequestError as exc:
        _log(f"POST esuat: {exc}")
        return 1

    _log("WMS este accesibil. Poti rula search cu SEND_EVENTS_TO_WMS=true.")
    return 0


def run_search(
    *,
    once: bool = False,
    include_image: bool = True,
    deposit_id: Optional[int] = None,
    pause_seconds: float = 1.5,
) -> int:
    service = FingerprintService()

    _log("Initializare senzor...")
    try:
        sensor = service.create_sensor()
    except Exception as exc:
        _log(f"Eroare la initializare: {exc}")
        return 1

    _log("Senzor gata.")
    _log_wms_config()
    if once:
        _log("Astept amprenta (o singura scanare)...")
    else:
        _log("Astept amprenta... (Ctrl+C pentru oprire)")

    while True:
        try:
            result = service.search_with_sensor(
                sensor,
                include_image=include_image,
                deposit_id=deposit_id,
            )
        except TimeoutError:
            _log("Timeout — incearca din nou.")
            if once:
                return 2
            continue
        except KeyboardInterrupt:
            _log("Oprire solicitata.")
            return 0
        except Exception as exc:
            _log(f"Eroare neasteptata la scanare: {exc}")
            return 1

        if result["match"]:
            _log(
                "Acces permis — "
                f"pozitie {result['position']}, scor {result['accuracy_score']}"
            )
            exit_code = 0
        else:
            _log(
                "Acces respins — amprenta necunoscuta "
                f"(scor {result['accuracy_score']})"
            )
            exit_code = 3

        if settings.send_events_to_wms:
            if result.get("wms_event_error"):
                _log(f"WMS: {result['wms_event_error']}")
            elif result.get("wms_event_sent"):
                _log("Eveniment trimis catre WMS.")

        if once:
            return exit_code

        _log("Astept urmatoarea amprenta...")
        time.sleep(pause_seconds)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wms-fingerprint",
        description="Comenzi locale pentru senzorul biometric WMS.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser(
        "search",
        help="Cauta amprenta si afiseaza loguri (acces permis / respins).",
    )
    search_parser.add_argument(
        "--once",
        action="store_true",
        help="Ruleaza o singura scanare, apoi iese.",
    )
    search_parser.add_argument(
        "--no-image",
        action="store_true",
        help="Nu captureaza imaginea (scanare mai rapida).",
    )
    search_parser.add_argument(
        "--deposit-id",
        type=int,
        default=None,
        help="ID depozit trimis la WMS impreuna cu evenimentul.",
    )
    search_parser.add_argument(
        "--pause",
        type=float,
        default=1.5,
        help="Pauza in secunde intre scanari in modul continuu (implicit 1.5).",
    )

    subparsers.add_parser(
        "check-wms",
        help="Testeaza conexiunea catre WMS (fara senzor).",
    )

    args = parser.parse_args(argv)

    if args.command == "check-wms":
        return run_check_wms()

    if args.command == "search":
        return run_search(
            once=args.once,
            include_image=not args.no_image,
            deposit_id=args.deposit_id,
            pause_seconds=args.pause,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
