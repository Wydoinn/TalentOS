# TalentOS Orchestration API

FastAPI service that coordinates the rest of TalentOS.

## What It Does

- manages jobs and job candidates
- calls the ATS service for ranking and resume insights
- manages scheduling, invites, booking, rescheduling, and cancellation
- creates and runs assessment sessions
- coordinates anti-spoofing before candidate assessments
- handles notifications and Gemini-powered hiring workflows
- exposes realtime assessment and proctoring flows

## Key Endpoints

- `GET /health`
- `POST /jobs`
- `GET /jobs`
- `POST /jobs/{job_id}/rank`
- `POST /schedules/slots`
- `POST /schedules/book`
- `POST /assessment/sessions`
- `POST /assessment/sessions/{session_id}/questions`
- `POST /assessment/sessions/{session_id}/answers`
- `POST /ai/chat`
- `GET /notifications/me`

## Requirements

- Python `3.10` only
- PostgreSQL
- Authentication API
- ATS Parser and Checker API
- Anti-Spoofing API
- Microsoft C++ Build Tools on Windows
- FFmpeg for local speech workflows

Optional:

- Gemini API key
- SMTP credentials

## Quick Start

Use the shared backend environment:

```powershell
py -3.10 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
cd backend\orchestration
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Open:

- `http://127.0.0.1:8001/docs`
- `http://127.0.0.1:8001/health`

Detailed setup is in `SETUP.md`.

## Notes

- this service reads shared settings from `backend/.env`
- local speech-to-text uses the shared Whisper model in `backend/models/faster-whisper-large-v3-turbo`
- manager data is scoped by manager ownership
