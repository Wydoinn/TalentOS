# ATS Parser and Checker API

FastAPI service for resume ingestion, ATS scoring, retrieval, and ranking.

## What It Does

- ingests resumes from `resumes/internal` and `resumes/external`
- parses PDF and DOCX resumes into structured candidate data
- builds local embeddings and reranker scores
- stores embeddings in Pinecone when configured
- uses optional Neo4j graph enrichment
- runs ATS checks against job descriptions
- stores feedback and report runs

## Key Endpoints

- `GET /api/health`
- `GET /api/resumes/status`
- `POST /api/resumes/sync`
- `POST /api/resumes/check`
- `GET /api/resumes/check/{report_run_id}`
- `GET /api/resumes/report/{report_run_id}/{candidate_id}`
- `POST /api/resumes/feedback`

## Requirements

- Python `3.10` only
- PostgreSQL
- local model files under `backend/models/`
- Microsoft C++ Build Tools on Windows

Optional:

- Pinecone
- Neo4j

For the full TalentOS backend stack, install FFmpeg too.

## Quick Start

Use the shared backend environment:

```powershell
py -3.10 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
cd backend\ats_parser_checker
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

Open:

- `http://127.0.0.1:8090/docs`
- `http://127.0.0.1:8090/api/health`

Detailed setup is in `SETUP.md`.

## Notes

- this service reads shared settings from `backend/.env`
- `backend/models/bge-large-en-v1.5` and `backend/models/bge-reranker-base` are required
- Pinecone is strongly recommended for semantic retrieval
- Neo4j is optional
