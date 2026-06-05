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
    include_image: Optional[bool] = None,
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
    if include_image is True or (
        include_image is None and settings.search_include_image
    ):
        _log("Captura imagine: activa (scanare mai lenta).")
    else:
        _log("Captura imagine: dezactivata (mod rapid).")
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


def run_templates() -> int:
    service = FingerprintService()

    _log("Citire memorie senzor...")
    try:
        result = service.list_templates()
    except Exception as exc:
        _log(f"Eroare: {exc}")
        return 1

    _log(f"Amprente in memorie: {result['template_count']}")
    _log(f"Capacitate senzor: {result['storage_capacity']}")
    positions = result.get("positions") or []
    if positions:
        _log(f"Pozitii ocupate: {', '.join(str(p) for p in positions)}")
    else:
        _log("Pozitii ocupate: (niciuna)")
    return 0


def run_clear(*, force: bool = False) -> int:
    service = FingerprintService()

    try:
        summary = service.list_templates()
    except Exception as exc:
        _log(f"Eroare la citire senzor: {exc}")
        return 1

    count = summary["template_count"]
    if count == 0:
        _log("Memoria senzorului este deja goala.")
        return 0

    positions = summary.get("positions") or []
    _log(f"Amprente in memorie: {count}")
    if positions:
        _log(f"Pozitii ocupate: {', '.join(str(p) for p in positions)}")

    if not force:
        _log("Stergere anulata. Ruleaza cu --yes pentru a confirma.")
        return 2

    try:
        result = service.clear_all_templates()
    except Exception as exc:
        _log(f"Eroare la stergere: {exc}")
        return 1

    _log(
        f"Memorie stearsa — {result['deleted_count']} amprente eliminate. "
        f"Ramase: {result['template_count']}."
    )
    return 0


def run_delete(position: int) -> int:
    service = FingerprintService()

    try:
        result = service.delete(position)
    except Exception as exc:
        _log(f"Eroare: {exc}")
        return 1

    _log(f"Amprenta de la pozitia {result['position']} a fost stearsa.")
    return 0


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
        "--with-image",
        action="store_true",
        help="Captureaza si trimite imaginea (mai lent, implicit dezactivat).",
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

    subparsers.add_parser(
        "templates",
        help="Afiseaza numarul si pozitiile amprentelor din senzor.",
    )

    clear_parser = subparsers.add_parser(
        "clear",
        help="Sterge toate amprentele din memoria senzorului.",
    )
    clear_parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma stergerea tuturor amprentelor.",
    )

    delete_parser = subparsers.add_parser(
        "delete",
        help="Sterge o amprenta dupa pozitie.",
    )
    delete_parser.add_argument(
        "position",
        type=int,
        help="Pozitia din memoria senzorului (ex: 0, 1, 2).",
    )

    args = parser.parse_args(argv)

    if args.command == "check-wms":
        return run_check_wms()

    if args.command == "templates":
        return run_templates()

    if args.command == "clear":
        return run_clear(force=args.yes)

    if args.command == "delete":
        if args.position < 0:
            _log("Pozitia trebuie sa fie >= 0.")
            return 1
        return run_delete(args.position)

    if args.command == "search":
        include_image = True if args.with_image else None
        return run_search(
            once=args.once,
            include_image=include_image,
            deposit_id=args.deposit_id,
            pause_seconds=args.pause,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
