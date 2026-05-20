# Bambu Fleet Manager

A production-grade FastAPI backend for managing a fleet of **Bambu Lab P1S** 3D printers. Supports multi-printer management, authenticated print job queuing, real-time MQTT status monitoring, and camera snapshots.

## Architecture

```
Client ──JWT──▶ FastAPI ──▶ PostgreSQL
                   │
                   ├──upload──▶ /tmp/bambu_uploads (shared volume)
                   │
                   └──enqueue──▶ Redis ──▶ Celery Worker
                                                │
                                          ┌─────┴──────┐
                                      FTP upload    MQTT cmds
                                          │              │
                                     Bambu P1S ◀────────┘
                                     (status/camera)
```

**Services:**
| Container | Role |
|-----------|------|
| `api` | FastAPI + Uvicorn — handles HTTP requests |
| `worker` | Celery — executes FTP uploads and monitors jobs |
| `beat` | Celery Beat — polls printer status every 30s |
| `flower` | Celery monitoring UI at `:5555` |
| `postgres` | Primary database |
| `redis` | Task broker + status cache |

## Prerequisites

- Docker 24+ and Docker Compose v2
- Bambu Lab P1S printers on LAN with **LAN Mode** enabled
- Printer `access_code` from the printer display (Settings → Network)
- Printer `serial_number` from the printer display

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/LennyBeto/bambu-fleet-manager
cd bambu-fleet-manager

# 2. Configure environment
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY:
#   SECRET_KEY=$(openssl rand -hex 32)

# 3. Build and start all services
make build
make up

# 4. Run database migrations
make migrate

# 5. Create your first admin user
make seed

# 6. Open the API docs
open http://localhost:8000/docs
```

## API Reference

All endpoints except `/health`, `/auth/register`, and `/auth/token` require a `Bearer` token in the `Authorization` header.

### Authentication

```http
POST /auth/register
Content-Type: application/json

{"email": "you@example.com", "password": "yourpass", "full_name": "Your Name"}
```

```http
POST /auth/token
Content-Type: application/json

{"email": "you@example.com", "password": "yourpass"}

→ {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600}
```

### Printer Management

```http
POST /printers/          # Register a printer
GET  /printers/          # List all printers
GET  /printers/{id}      # Get a printer
PATCH /printers/{id}     # Update printer settings
DELETE /printers/{id}    # Remove printer
```

**Register printer example:**

```json
{
  "name": "P1S Alpha",
  "serial_number": "00M00A123456789",
  "model": "P1S",
  "access_code": "12345678",
  "local_ip": "192.168.1.100",
  "location": "Lab A"
}
```

### Print Jobs

```http
POST /jobs/upload        # Upload print file — multipart/form-data
GET  /jobs/              # List all jobs (filter by ?printer_id=)
GET  /jobs/{id}          # Job status + progress
POST /jobs/{id}/cancel   # Cancel a pending/printing job
```

**Upload a print file:**

```bash
curl -X POST http://localhost:8000/jobs/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "printer_id=<uuid>" \
  -F "plate_type=Cool Plate" \
  -F "use_ams=true" \
  -F "file=@my_model.gcode"
```

Response (HTTP 202 — Accepted, queued):

```json
{
  "id": "3fa85f64-...",
  "printer_id": "...",
  "original_filename": "my_model.gcode",
  "status": "pending",
  "progress_percent": 0,
  "celery_task_id": "abc123",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Monitoring

```http
GET /printers/{id}/status            # Latest status (cached, fast)
GET /printers/{id}/status?force_refresh=true  # Live MQTT fetch (~3s)
GET /printers/{id}/snapshot          # Live JPEG snapshot (base64)
```

**Status response:**

```json
{
  "printer_id": "...",
  "online": true,
  "state": "PRINTING",
  "print_percent": 47,
  "layer_num": 128,
  "total_layer_count": 270,
  "remaining_time_minutes": 43,
  "temperatures": {
    "nozzle_actual": 220.0,
    "nozzle_target": 220.0,
    "bed_actual": 60.0,
    "bed_target": 60.0
  }
}
```

## Bambu Lab Protocol Notes

### LAN Mode Setup (required)

1. On the printer: **Settings → Network → LAN Mode Liveview** → Enable
2. Note the `access_code` shown on screen (8 alphanumeric characters)
3. Note the `serial_number` (14 characters, starts with `00M`)

### MQTT

- **Cloud broker:** `us.mqtt.bambulab.com:8883` (TLS)
- **LAN broker:** `<printer_ip>:8883` (TLS, self-signed cert — verification disabled)
- Auth: username `bblp`, password = `access_code`
- Subscribe topic: `device/{serial}/report`
- Command topic: `device/{serial}/request`

### FTP

- **Protocol:** FTPS (FTP over implicit TLS)
- **Port:** 990
- **Auth:** username `bblp`, password = `access_code`
- **Upload dir:** `/model/`
- Self-signed cert — TLS verification disabled

## Development (without Docker)

```bash
# Install dependencies
pip install poetry
poetry install

# Start services (Postgres + Redis only)
docker compose up postgres redis -d

# Export env vars
export $(cat .env | xargs)
export DATABASE_URL=postgresql+asyncpg://bambu:bambu_pass@localhost:5432/bambu

# Run migrations
alembic upgrade head

# Start API
uvicorn app.main:app --reload --port 8000

# Start Celery worker (separate terminal)
celery -A app.workers.celery_app.celery_app worker --loglevel=debug

# Start Beat (separate terminal)
celery -A app.workers.celery_app.celery_app beat --loglevel=info
```

## Testing

```bash
make test
# or locally:
pytest tests/ -v --cov=app --cov-report=html
```

## Deployment Checklist

- [ ] Set a strong `SECRET_KEY` (32+ random bytes)
- [ ] Change all default passwords in `docker-compose.yml`
- [ ] Set `DEBUG=false` in `.env`
- [ ] Restrict `allow_origins` in `app/main.py` to your frontend domain
- [ ] Add HTTPS via nginx/Caddy reverse proxy in front of the API
- [ ] Consider encrypting `access_code` at rest (PostgreSQL `pgcrypto`)
- [ ] Set up log aggregation (e.g. Loki + Grafana or Datadog)
- [ ] Configure Flower with a strong `--basic_auth` password
- [ ] Mount `upload_data` volume to a persistent disk

## Project Structure

```
app/
├── core/        # Security, logging, custom exceptions
├── models/      # SQLAlchemy ORM models
├── schemas/     # Pydantic request/response schemas
├── routers/     # FastAPI route handlers
├── services/    # Business logic (MQTT, FTP, camera, DB)
└── workers/     # Celery tasks and Beat schedule
```

## License

MIT
