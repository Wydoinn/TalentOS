# TalentOS Setup Guide

This guide is for running the full TalentOS stack from this repository.

## 1. Requirements

Install these first:

- Python `3.10` only
- Node.js `20+`
- npm
- PostgreSQL
- FFmpeg
- Microsoft C++ Build Tools on Windows

Optional but used by some features:

- Pinecone
- Neo4j
- Redis
- Gemini API key

Important:

- Python `3.10` is the only supported version for this repo.
- On Windows, install the Visual Studio Build Tools workload for C++ before installing Python packages.
- FFmpeg must be available on your system `PATH` because the anti-spoofing pipeline depends on it.

Quick checks:

```powershell
python --version
node -v
npm -v
ffmpeg -version
```

The Python version should report `3.10.x`.

If `python --version` does not point to Python 3.10 on Windows, use `py -3.10` when creating the virtual environment.

## 2. Repository Overview

Main folders in this repo:

- `frontend/`: Angular app for both manager and candidate flows.
- `backend/authentication/`: OTP auth and face verification service.
- `backend/orchestration/`: jobs, scheduling, assessment, AI, and notifications service.
- `backend/anti_spoofing/`: liveness and anti-spoofing service.
- `backend/ats_parser_checker/`: resume parsing and ATS ranking service.
- `backend/models/`: shared local model cache for face, audio, speech-to-text, embeddings, and reranking. See `backend/models/README.md` for download sources.

The backend uses one shared dependency file:

```text
backend/requirements.txt
```

The repo already includes these environment templates:

- `backend/.env.example`
- `frontend/.env.example`

## 3. Create the Backend Virtual Environment

The Windows launcher `run-all.ps1` expects this exact path:

```text
backend/.venv
```

From the repository root:

```powershell
py -3.10 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

If you prefer activating the environment:

```powershell
backend\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

## 4. Install Frontend Dependencies

From the repository root:

```powershell
cd frontend
npm install
cd ..
```

## 5. Create Environment Files

Copy the templates:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

## 6. Configure `backend/.env`

The backend services read from `backend/.env`.

### Shared credentials

Set these if you use Pinecone:

```env
AUTH_PINECONE_API_KEY=...
ATS_PINECONE_API_KEY=...
```

### Authentication service

Minimum important values:

```env
AUTH_DATABASE_URL=postgresql+psycopg2://postgres:YOUR_DB_PASSWORD@localhost:5432/authentication
AUTH_JWT_SECRET_KEY=...
AUTH_OTP_SECRET=...
AUTH_SMTP_HOST=smtp.gmail.com
AUTH_SMTP_PORT=587
AUTH_SMTP_USERNAME=your_email@gmail.com
AUTH_SMTP_PASSWORD=your_app_password
AUTH_SMTP_FROM_EMAIL=your_email@gmail.com
AUTH_PINECONE_INDEX_NAME=authentication
AUTH_ORCHESTRATION_SERVICE_URL=http://127.0.0.1:8001
AUTH_ORCHESTRATION_SERVICE_TOKEN=...
```

Notes:

- SMTP is required for OTP flows.
- Pinecone is required for candidate face registration and verification.
- `AUTH_FACE_MODEL_ROOT` defaults to `../models`.

### ATS Parser and Checker service

Minimum important values:

```env
ATS_DATABASE_URL=postgresql+asyncpg://postgres:YOUR_DB_PASSWORD@localhost:5432/ats_parser_checker
ATS_EMBEDDING_MODEL_DIR=../models/bge-large-en-v1.5
ATS_RERANKER_MODEL_DIR=../models/bge-reranker-base
ATS_RESUME_SOURCE_DIR=./resumes
```

Optional but common:

```env
ATS_PINECONE_API_KEY=...
ATS_PINECONE_INDEX_NAME=candidate-resumes
ATS_NEO4J_URI=neo4j+s://...
ATS_NEO4J_USERNAME=neo4j
ATS_NEO4J_PASSWORD=...
```

Notes:

- PostgreSQL is required.
- Pinecone is strongly recommended for semantic retrieval.
- Neo4j is optional.

### Orchestration service

Minimum important values:

```env
ORCH_DATABASE_URL=postgresql+asyncpg://postgres:YOUR_DB_PASSWORD@localhost:5432/orchestration
ORCH_AUTH_JWT_SECRET_KEY=...
ORCH_INTERNAL_SERVICE_TOKEN=...
ORCH_AUTHENTICATION_SERVICE_URL=http://127.0.0.1:8000
ORCH_ATS_SERVICE_URL=http://127.0.0.1:8090
ORCH_ANTI_SPOOFING_SERVICE_URL=http://127.0.0.1:8080
ORCH_CANDIDATE_PORTAL_BASE_URL=http://localhost:3000
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

Notes:

- Gemini is needed for AI-assisted features.
- SMTP is needed for invite and reminder emails.
- Orchestration also uses the local Whisper model from `backend/models/faster-whisper-large-v3-turbo`.

### Anti-Spoofing service

Minimum important values:

```env
ANTI_SPOOFING_JWT_SECRET_KEY=...
ANTI_SPOOFING_MODELS_DIR=../models
ANTI_SPOOFING_INSIGHTFACE_MODEL_DIR=../models/buffalo_l
ANTI_SPOOFING_FACE_SPOOF_MODEL_PATH=../models/anti-spoof-mn3.onnx
ANTI_SPOOFING_AUDIO_SPOOF_MODEL_DIR=../models/mms-300m-anti-deepfake
ANTI_SPOOFING_STT_MODEL_DIR=../models/faster-whisper-large-v3-turbo
ANTI_SPOOFING_SESSION_STORE_BACKEND=memory
```

Optional:

```env
ANTI_SPOOFING_REDIS_URL=redis://localhost:6379/0
```

Notes:

- Redis is optional unless you want persistent session storage.
- FFmpeg must be installed before using media analysis endpoints.

## 7. Configure `frontend/.env`

The frontend uses:

```env
APP_URL=http://localhost:3000
AUTH_API_BASE_URL=http://127.0.0.1:8000
ORCHESTRATION_API_BASE_URL=http://127.0.0.1:8001
DEV_HOST=localhost
```

For local development, the defaults in `frontend/.env.example` are already correct.

## 8. Create PostgreSQL Databases

Create these databases:

```sql
CREATE DATABASE authentication;
CREATE DATABASE orchestration;
CREATE DATABASE ats_parser_checker;
```

The services create their tables on startup.

## 9. Verify Local Model Assets

TalentOS expects these local model files and folders under `backend/models/` after you download them:

```text
backend/models/
  anti-spoof-mn3.onnx
  bge-large-en-v1.5/
  bge-reranker-base/
  buffalo_l/
  faster-whisper-large-v3-turbo/
  mms-300m-anti-deepfake/
```

What they are used for:

- `buffalo_l/`: face detection and embeddings
- `anti-spoof-mn3.onnx`: face anti-spoof model
- `mms-300m-anti-deepfake/`: audio anti-spoof model
- `faster-whisper-large-v3-turbo/`: speech-to-text for anti-spoofing and orchestration
- `bge-large-en-v1.5/`: ATS embedding model
- `bge-reranker-base/`: ATS reranker model

Download links and model notes live in `backend/models/README.md`.

## 10. Start the Stack

### Windows

From the repository root:

```powershell
./run-all.ps1
```

Optional:

```powershell
./run-all.ps1 -SkipFrontendInstall
```

### macOS / Linux

From the repository root:

```bash
./run-all.sh
```

Optional:

```bash
./run-all.sh --skip-frontend
./run-all.sh --skip-backend
```

Note:

- `run-all.sh` uses the active `python3` and `pip`, so make sure your shell is using Python 3.10 before you run it.

## 11. Start Services Manually

If you do not want to use the helper scripts, start each service in a separate terminal.

Authentication:

```powershell
cd backend\authentication
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Anti-spoofing:

```powershell
cd backend\anti_spoofing
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

ATS parser:

```powershell
cd backend\ats_parser_checker
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

Orchestration:

```powershell
cd backend\orchestration
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Frontend:

```powershell
cd frontend
npm run dev
```

## 12. Local URLs

- Frontend: `http://localhost:3000`
- Authentication docs: `http://127.0.0.1:8000/docs`
- Orchestration docs: `http://127.0.0.1:8001/docs`
- Anti-Spoofing docs: `http://127.0.0.1:8080/docs`
- ATS docs: `http://127.0.0.1:8090/docs`
- ATS health: `http://127.0.0.1:8090/api/health`

## 13. Run Tests

Run backend tests from each service folder because the repo contains multiple top-level `app` packages:

```powershell
cd backend\authentication
..\.venv\Scripts\python.exe -m pytest -q

cd ..\anti_spoofing
..\.venv\Scripts\python.exe -m pytest -q

cd ..\ats_parser_checker
..\.venv\Scripts\python.exe -m pytest -q

cd ..\orchestration
..\.venv\Scripts\python.exe -m pytest -q
```

Frontend:

```powershell
cd frontend
npm test
```

## 14. Common Problems

### Python install issues on Windows

If package installation fails with build or compiler errors, install Microsoft C++ Build Tools and then reinstall the backend dependencies.

### FFmpeg not found

If audio or video processing fails, confirm this works:

```powershell
ffmpeg -version
```

### Wrong Python version

If you use Python 3.11 or newer, some ML or media dependencies may fail to install or run correctly. Recreate the virtual environment with Python `3.10`.

### Missing model files

If anti-spoofing, ATS, transcription, or face features fail at startup, verify the required folders exist in `backend/models/` and match the model names listed in `backend/models/README.md`.

### External services not configured

Some features stay limited until these are configured:

- SMTP for OTP and notifications
- Pinecone for face vectors and ATS semantic retrieval
- Neo4j for ATS graph enrichment
- Gemini for orchestration AI features
- Redis for persistent anti-spoof sessions
