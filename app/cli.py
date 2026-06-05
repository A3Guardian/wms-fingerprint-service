import argparse
import sys
import time
from datetime import datetime
from typing import Optional

from app.config import settings
from app.services.fingerprint_service import FingerprintService


def _log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


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
            _log(f"Eroare: {exc}")
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

    args = parser.parse_args(argv)

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
