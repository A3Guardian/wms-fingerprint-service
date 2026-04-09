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
