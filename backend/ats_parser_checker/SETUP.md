# ATS Parser and Checker Setup

This guide sets up the ATS parser and checker service only.

## 1. Requirements

Install or prepare these first:

- Python `3.10` only
- PostgreSQL
- local model files under `backend/models/`
- Microsoft C++ Build Tools on Windows

Optional:

- Pinecone
- Neo4j

For the full TalentOS backend stack, install FFmpeg too.

Important:

- Python `3.10` is the only supported version.

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

## 4. Configure ATS Settings

Minimum important values:

```env
ATS_DATABASE_URL=postgresql+asyncpg://postgres:YOUR_DB_PASSWORD@localhost:5432/ats_parser_checker
ATS_EMBEDDING_MODEL_DIR=../models/bge-large-en-v1.5
ATS_RERANKER_MODEL_DIR=../models/bge-reranker-base
ATS_RESUME_SOURCE_DIR=./resumes
```

Optional integrations:

```env
ATS_PINECONE_API_KEY=...
ATS_PINECONE_INDEX_NAME=candidate-resumes
ATS_PINECONE_NAMESPACE=candidates
ATS_NEO4J_URI=neo4j+s://...
ATS_NEO4J_USERNAME=neo4j
ATS_NEO4J_PASSWORD=...
```

## 5. Create the Database

```sql
CREATE DATABASE ats_parser_checker;
```

The service creates its tables automatically on startup.

## 6. Verify Local Model Files

These must exist:

- `backend/models/bge-large-en-v1.5`
- `backend/models/bge-reranker-base`

## 7. Resume Source Folders

The service watches:

- `resumes/internal`
- `resumes/external`

Supported files:

- `.pdf`
- `.docx`

## 8. Run the Service

From the repository root:

```powershell
cd backend\ats_parser_checker
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

Useful URLs:

- `http://127.0.0.1:8090/docs`
- `http://127.0.0.1:8090/api/health`

## 9. Run Tests

```powershell
cd backend\ats_parser_checker
..\.venv\Scripts\python.exe -m pytest -q
```

## 10. Troubleshooting

### Health is degraded

Check:

- `ATS_DATABASE_URL`
- model directories
- optional Pinecone or Neo4j credentials

### Semantic retrieval is weak or unavailable

Check the `ATS_PINECONE_*` settings.

### Wrong Python version

Recreate `backend/.venv` with Python `3.10`.
