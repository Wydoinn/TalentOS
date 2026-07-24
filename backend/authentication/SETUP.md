# Authentication API Setup

This guide sets up the authentication service only.

## 1. Requirements

Install these first:

- Python `3.10` only
- PostgreSQL
- Pinecone
- SMTP credentials
- Microsoft C++ Build Tools on Windows

For the full TalentOS backend stack, install FFmpeg too.

Important:

- Python `3.10` is the only supported version.
- On Windows, install the Visual Studio C++ Build Tools workload before installing `backend/requirements.txt`.

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

## 4. Configure Authentication Settings

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
AUTH_PINECONE_API_KEY=...
AUTH_PINECONE_INDEX_NAME=authentication
AUTH_PINECONE_NAMESPACE=authentication
AUTH_ORCHESTRATION_SERVICE_URL=http://127.0.0.1:8001
AUTH_ORCHESTRATION_SERVICE_TOKEN=...
```

Useful defaults already in the template:

- `AUTH_FACE_MODEL_ROOT=../models`
- `AUTH_FACE_SIMILARITY_THRESHOLD=0.6`
- `AUTH_MAX_UPLOAD_BYTES=5242880`

## 5. Create the Database

```sql
CREATE DATABASE authentication;
```

The service creates its tables automatically on startup.

## 6. Prepare Pinecone

Candidate face embeddings are stored in Pinecone.

Expected index shape:

- dimension `512`
- metric `cosine`
- one vector per candidate

By default, the service can auto-create the configured index when credentials allow it.

## 7. Run the Service

From the repository root:

```powershell
cd backend\authentication
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Useful URLs:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

## 8. Run Tests

```powershell
cd backend\authentication
..\.venv\Scripts\python.exe -m pytest -q
```

The tests use SQLite and mocks, so PostgreSQL, Pinecone, and SMTP are not required for test runs.

## 9. Troubleshooting

### OTP endpoints return `503`

SMTP is missing or invalid.

### Face registration or verification fails

Check:

- `AUTH_PINECONE_API_KEY`
- `AUTH_PINECONE_INDEX_NAME`
- `AUTH_PINECONE_NAMESPACE`
- Pinecone index dimension `512`

### Wrong Python version

Recreate `backend/.venv` with Python `3.10`.
