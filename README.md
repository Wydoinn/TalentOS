# TalentOS

TalentOS is a local AI recruitment platform with a single Angular frontend and four FastAPI backend services.

## What Is In This Repo

- `frontend/`: Angular 21 app for project managers and candidates.
- `backend/authentication/`: OTP login and candidate face registration/verification.
- `backend/orchestration/`: jobs, scheduling, assessments, notifications, AI workflows, and realtime coordination.
- `backend/anti_spoofing/`: video and audio liveness / anti-spoofing checks.
- `backend/ats_parser_checker/`: resume parsing, ATS scoring, retrieval, and ranking.
- `backend/models/`: shared local model cache used by the backend services. See `backend/models/README.md` for the model list and download sources.
- `run-all.ps1` and `run-all.sh`: helper scripts to start the stack locally.

## Required Tools

- Python `3.10` only
- Node.js `20+`
- PostgreSQL
- FFmpeg on your system `PATH`
- Microsoft C++ Build Tools on Windows

Optional integrations used by some flows:

- Pinecone
- Neo4j
- Gemini API
- Redis

## Quick Start

1. Read [SETUP.md](SETUP.md).
2. Create `backend/.venv` with Python 3.10.
3. Install backend dependencies from `backend/requirements.txt`.
4. Install frontend dependencies in `frontend/`.
5. Copy and update:
   - `backend/.env.example` -> `backend/.env`
   - `frontend/.env.example` -> `frontend/.env`
6. Create these PostgreSQL databases:
   - `authentication`
   - `orchestration`
   - `ats_parser_checker`
7. Download the required local models into `backend/models/` using `backend/models/README.md`.
8. Start the stack:
   - Windows: `./run-all.ps1`
   - macOS/Linux: `./run-all.sh`

## Default Local Ports

- Frontend: `http://localhost:3000`
- Authentication API: `http://127.0.0.1:8000`
- Orchestration API: `http://127.0.0.1:8001`
- Anti-Spoofing API: `http://127.0.0.1:8080`
- ATS Parser API: `http://127.0.0.1:8090`

## Repository Map

```text
TalentOS/
  backend/
    .env.example
    requirements.txt
    anti_spoofing/
    ats_parser_checker/
    authentication/
    models/
    orchestration/
  frontend/
    .env.example
    src/
  run-all.ps1
  run-all.sh
  README.md
  SETUP.md
```

## Notes

- Use Python `3.10` only. Other versions are not supported for this repo's ML and media stack.
- `backend/models/` is required locally, but the model files are not checked in. Use `backend/models/README.md` to download the required assets.
- The frontend talks to authentication on `8000` and orchestration on `8001`.
- Service-level READMEs and SETUP guides still exist inside `backend/*`, but the root docs should be your main starting point.
