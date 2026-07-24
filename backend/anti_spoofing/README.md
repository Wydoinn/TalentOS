# Anti-Spoofing API

FastAPI service for session-based liveness and anti-spoofing checks.

## What It Does

- creates short-lived verification sessions
- issues spoken phrase or digit challenges
- analyzes recorded video clips for face, voice, challenge, tamper, and identity signals
- returns `PASS`, `FAIL`, or `FLAG`
- exposes status and finalization endpoints for orchestration

## Key Endpoints

- `POST /sessions`
- `POST /sessions/{session_id}/challenge`
- `POST /sessions/{session_id}/analyze`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/finalize`
- `GET /health`
- `GET /ready`

## Requirements

- Python `3.10` only
- FFmpeg on your system `PATH`
- local model files under `backend/models/`
- Microsoft C++ Build Tools on Windows

Optional:

- Redis for persistent session storage

## Quick Start

Use the shared backend environment:

```powershell
py -3.10 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
cd backend\anti_spoofing
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open:

- `http://127.0.0.1:8080/docs`
- `http://127.0.0.1:8080/health`
- `http://127.0.0.1:8080/ready`

Detailed setup is in `SETUP.md`.

## Notes

- this service reads shared settings from `backend/.env`
- local model paths default to the shared `backend/models/` folder
- FFmpeg is required before media analysis will work
