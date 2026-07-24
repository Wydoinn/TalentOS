# TalentOS Backend Setup

This guide sets up the backend stack only.

## 1. Requirements

Install these first:

- Python `3.10` only
- PostgreSQL
- FFmpeg
- Microsoft C++ Build Tools on Windows

Optional but used by some backend features:

- Pinecone
- Neo4j
- Redis
- Gemini API key
- SMTP credentials

Important:

- Python `3.10` is the only supported version for this backend.
- FFmpeg must be available on your system `PATH`.
- On Windows, install the Visual Studio C++ Build Tools workload before installing the Python packages.

Quick checks:

```powershell
python --version
ffmpeg -version
```

The Python version should report `3.10.x`.

## 2. Create the Shared Backend Virtual Environment

From the repository root:

```powershell
py -3.10 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## 3. Create the Shared Backend Environment File

Copy the template:

```powershell
Copy-Item backend\.env.example backend\.env
```

All backend services read from `backend/.env`.

## 4. Create PostgreSQL Databases

Create these databases:

```sql
CREATE DATABASE authentication;
CREATE DATABASE orchestration;
CREATE DATABASE ats_parser_checker;
```

The services create their own tables on startup.

## 5. Verify Local Model Files

The backend expects these local model assets:

```text
backend/models/
  anti-spoof-mn3.onnx
  bge-large-en-v1.5/
  bge-reranker-base/
  buffalo_l/
  faster-whisper-large-v3-turbo/
  mms-300m-anti-deepfake/
```

These are used for:

- face detection and embeddings
- face anti-spoofing
- audio anti-spoofing
- local speech-to-text
- ATS embeddings and reranking

## 6. Minimum `backend/.env` Areas to Fill

Authentication:

- `AUTH_DATABASE_URL`
- `AUTH_JWT_SECRET_KEY`
- `AUTH_OTP_SECRET`
- `AUTH_SMTP_*`
- `AUTH_PINECONE_*`

ATS Parser and Checker:

- `ATS_DATABASE_URL`
- `ATS_EMBEDDING_MODEL_DIR`
- `ATS_RERANKER_MODEL_DIR`
- optional `ATS_PINECONE_*`
- optional `ATS_NEO4J_*`

Orchestration:

- `ORCH_DATABASE_URL`
- `ORCH_AUTH_JWT_SECRET_KEY`
- `ORCH_INTERNAL_SERVICE_TOKEN`
- `ORCH_AUTHENTICATION_SERVICE_URL`
- `ORCH_ATS_SERVICE_URL`
- `ORCH_ANTI_SPOOFING_SERVICE_URL`
- optional `ORCH_GEMINI_API_KEY`
- optional `ORCH_SMTP_*`

Anti-Spoofing:

- `ANTI_SPOOFING_JWT_SECRET_KEY`
- `ANTI_SPOOFING_MODELS_DIR`
- `ANTI_SPOOFING_FACE_SPOOF_MODEL_PATH`
- `ANTI_SPOOFING_AUDIO_SPOOF_MODEL_DIR`
- `ANTI_SPOOFING_STT_MODEL_DIR`
- optional `ANTI_SPOOFING_REDIS_URL`

## 7. Run Backend Services

Authentication:

```powershell
cd backend\authentication
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Anti-Spoofing:

```powershell
cd backend\anti_spoofing
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

ATS Parser and Checker:

```powershell
cd backend\ats_parser_checker
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

Orchestration:

```powershell
cd backend\orchestration
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## 8. Docs URLs

- Authentication: `http://127.0.0.1:8000/docs`
- Orchestration: `http://127.0.0.1:8001/docs`
- Anti-Spoofing: `http://127.0.0.1:8080/docs`
- ATS Parser and Checker: `http://127.0.0.1:8090/docs`

## 9. Run Tests

Run tests from each service folder:

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

## 10. Common Problems

### Python package install fails on Windows

Install Microsoft C++ Build Tools, then reinstall `backend/requirements.txt`.

### FFmpeg not found

Install FFmpeg and confirm:

```powershell
ffmpeg -version
```

### Wrong Python version

If you use Python 3.11 or newer, recreate `backend/.venv` with Python `3.10`.

### Missing model files

If startup fails in anti-spoofing, ATS, or transcription features, verify `backend/models/` is populated.
