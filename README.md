# WMS Fingerprint Service

Serviciu FastAPI pentru integrare biometrica cu senzor compatibil `pyfingerprint`.

## Setup local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn[standard] python-dotenv pydantic-settings httpx pyfingerprint
pip freeze > requirements.txt
```

## Rulare

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

## Comanda locala `search` (loguri in terminal)

Pentru verificare directa pe Raspberry Pi (fara HTTP), ruleaza:

```bash
source .venv/bin/activate
python -m app.cli search
```

Exemple de loguri afisate:

- `Astept amprenta...`
- `Acces permis — pozitie 3, scor 127`
- `Acces respins — amprenta necunoscuta`
- `Timeout — incearca din nou.`

Optiuni utile:

```bash

python -m app.cli search --once


python -m app.cli search --deposit-id 1

python -m app.cli search --no-image
```

Daca `SEND_EVENTS_TO_WMS=true` in `.env`, comanda trimite automat evenimentele la WMS, la fel ca endpointul `POST /search`.

**Nota:** inrolarea amprentelor se face din WMS (asociata unui utilizator). Comanda CLI `search` este pentru verificare acces la usa; enroll-ul local din CLI nu leaga amprenta de un utilizator WMS.

### Enroll din WMS (pas cu pas)

WMS foloseste sesiuni in 3 pasi, astfel incat in interfata apar logurile in timp real:

1. `POST /enroll/session` — porneste sesiunea
2. `POST /enroll/session/{id}/first-scan` — prima scanare
3. `POST /enroll/session/{id}/second-scan` — a doua scanare + salvare in WMS pentru utilizatorul selectat

Endpointul vechi `POST /enroll` (o singura cerere) ramane disponibil pentru apeluri din WMS.

## Pornire automata (systemd)

Inlocuieste in `deploy/wms-fingerprint.service` calea `/home/pi/wms-fingerprint-service` si userul `pi` daca proiectul sta altundeva sau rulezi sub alt cont.

```bash
sudo cp deploy/wms-fingerprint.service /etc/systemd/system/wms-fingerprint.service
sudo systemctl daemon-reload
sudo systemctl enable wms-fingerprint.service
sudo systemctl start wms-fingerprint.service
sudo systemctl status wms-fingerprint.service
```

Loguri: `journalctl -u wms-fingerprint.service -f`

## Test endpoint

```bash
curl http://127.0.0.1:8100/health
```

## Endpointuri biometrice

- `POST /enroll` - citeste aceeasi amprenta de 2 ori, salveaza template-ul si poate intoarce imaginea scanata (base64 PNG)
- `POST /search` - cauta amprenta in baza senzorului si poate intoarce imaginea scanata (base64 PNG)
- `DELETE /delete` - sterge un template dupa pozitie

Exemple:

```bash
curl -X POST http://127.0.0.1:8100/enroll \
  -H "Content-Type: application/json" \
  -d '{"include_image": true}'
curl -X POST http://127.0.0.1:8100/search \
  -H "Content-Type: application/json" \
  -d '{"include_image": true, "deposit_id": 1}'
curl -X DELETE http://127.0.0.1:8100/delete \
  -H "Content-Type: application/json" \
  -d '{"position": 3}'
```

Cand `SEND_EVENTS_TO_WMS=true`, endpointul `/search` trimite automat evenimentul la WMS (`POST /api/biometric/events`) incluzand si `fingerprint_image_base64`.

## Configurare senzor

Seteaza in `.env`:

```env
SERVICE_PORT=8100
WMS_API_BASE_URL=http://192.168.68.41
WMS_EVENTS_ENDPOINT=/api/biometric/events
WMS_DEVICE_ID=pi-fingerprint-01
WMS_DEVICE_SECRET=change_me
SEND_EVENTS_TO_WMS=false
FINGERPRINT_SERIAL_PORT=/dev/ttyUSB0
FINGERPRINT_BAUD_RATE=57600
FINGERPRINT_SENSOR_ADDRESS=4294967295
FINGERPRINT_SENSOR_PASSWORD=0
FINGERPRINT_READ_TIMEOUT_SECONDS=15
```
