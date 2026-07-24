# TalentOS Backend

The TalentOS backend is a four-service FastAPI stack with shared dependencies, shared environment files, and shared local model assets.

## Services

- `authentication/`: OTP login plus candidate face registration and face verification
- `orchestration/`: jobs, scheduling, assessments, notifications, AI workflows, and realtime coordination
- `anti_spoofing/`: liveness and anti-spoofing analysis for recorded interview clips
- `ats_parser_checker/`: resume parsing, ATS scoring, retrieval, and candidate ranking
- `models/`: local model files used by the ML-backed services

## Shared Backend Files

- `.env.example`: backend environment template
- `.env`: local backend environment file
- `requirements.txt`: shared Python dependencies

## Requirements

- Python `3.10` only
- PostgreSQL
- Microsoft C++ Build Tools on Windows
- FFmpeg on your system `PATH`

Optional integrations:

- Pinecone
- Neo4j
- Redis
- Gemini API
- SMTP credentials

## Default Local Ports

- Authentication: `8000`
- Orchestration: `8001`
- Anti-Spoofing: `8080`
- ATS Parser and Checker: `8090`

## Quick Start

1. Follow [SETUP.md](SETUP.md).
2. Create `backend/.venv` with Python 3.10.
3. Install `backend/requirements.txt`.
4. Copy `backend/.env.example` to `backend/.env`.
5. Create the PostgreSQL databases.
6. Verify the local model files under `backend/models/`.
7. Start the services you need.

## Notes

- Python `3.10` is the only supported version for the backend stack.
- FFmpeg is required for anti-spoofing and local speech workflows.
- On Windows, install Microsoft C++ Build Tools before installing backend Python packages.
- Each service also has its own `README.md` and `SETUP.md` inside its folder.
