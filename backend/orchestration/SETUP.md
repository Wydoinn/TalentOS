# Orchestration API Setup

This guide sets up the orchestration service only.

## 1. Requirements

Install or prepare these first:

- Python `3.10` only
- PostgreSQL
- Authentication API
- ATS Parser and Checker API
- Anti-Spoofing API
- FFmpeg
- Microsoft C++ Build Tools on Windows

Optional:

- Gemini API key
- SMTP credentials

Important:

- Python `3.10` is the only supported version.
- FFmpeg is required for local audio transcription workflows.

## 2. Create the Shared Backend Virtual Environment

From the repository root:

```powershell
py -3.10 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## 3. Create `backend/.env`

Copy the shared backend template:

```powershell
Copy-Item backend\.env.example backend\.env
```

This service reads its settings from `backend/.env`.

## 4. Configure Orchestration Settings

Minimum important values:

```env
ORCH_DATABASE_URL=postgresql+asyncpg://postgres:YOUR_DB_PASSWORD@localhost:5432/orchestration
ORCH_AUTH_JWT_SECRET_KEY=...
ORCH_INTERNAL_SERVICE_TOKEN=...
ORCH_AUTHENTICATION_SERVICE_URL=http://127.0.0.1:8000
ORCH_ATS_SERVICE_URL=http://127.0.0.1:8090
ORCH_ANTI_SPOOFING_SERVICE_URL=http://127.0.0.1:8080
ORCH_CANDIDATE_PORTAL_BASE_URL=http://localhost:3000
ORCH_STT_MODEL_DIR=../models/faster-whisper-large-v3-turbo
```

Optional but common:

```env
ORCH_GEMINI_API_KEY=...
ORCH_SMTP_HOST=smtp.gmail.com
ORCH_SMTP_PORT=587
ORCH_SMTP_USERNAME=your_email@gmail.com
ORCH_SMTP_PASSWORD=your_app_password
ORCH_SMTP_FROM_EMAIL=your_email@gmail.com
```

## 5. Create the Database

```sql
CREATE DATABASE orchestration;
```

The service creates its tables and seeds built-in roles on startup.

## 6. Start Dependency Services

Before starting orchestration, make sure these are reachable:

- authentication on `8000`
- anti-spoofing on `8080`
- ATS parser and checker on `8090`

## 7. Run the Service

From the repository root:

```powershell
cd backend\orchestration
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Useful URLs:

- `http://127.0.0.1:8001/docs`
- `http://127.0.0.1:8001/health`

## 8. Run Tests

```powershell
cd backend\orchestration
..\.venv\Scripts\python.exe -m pytest -q
```

The tests use SQLite and mocked downstream clients for most scenarios.

## 9. Troubleshooting

### Health is degraded

Check:

- `ORCH_AUTHENTICATION_SERVICE_URL`
- `ORCH_ATS_SERVICE_URL`
- `ORCH_ANTI_SPOOFING_SERVICE_URL`

### AI endpoints do not work

Check `ORCH_GEMINI_API_KEY`.

### Invite or reminder emails are not sent

Check the `ORCH_SMTP_*` values.

### Wrong Python version

Recreate `backend/.venv` with Python `3.10`.
