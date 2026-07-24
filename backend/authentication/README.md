# Authentication API

FastAPI service for passwordless OTP authentication and candidate face verification.

## What It Does

- sends and verifies sign-up OTPs
- sends and verifies login OTPs
- supports OTP-only authentication for managers
- supports face registration and face verification for candidates
- stores users and OTP data in PostgreSQL
- stores candidate face embeddings in Pinecone

## Key Endpoints

- `POST /auth/signup/send-otp`
- `POST /auth/signup/verify-otp`
- `POST /auth/login/send-otp`
- `POST /auth/login/verify-otp`
- `POST /candidate/register-face`
- `POST /candidate/verify-face`
- `GET /health`

## Requirements

- Python `3.10` only
- PostgreSQL
- Pinecone
- SMTP credentials
- Microsoft C++ Build Tools on Windows

For the full TalentOS backend stack, also install FFmpeg.

## Quick Start

Use the shared backend environment:

```powershell
py -3.10 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
cd backend\authentication
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

Detailed setup is in `SETUP.md`.

## Notes

- this service reads shared settings from `backend/.env`
- shared Python dependencies come from `backend/requirements.txt`
- raw face images are not stored
- Pinecone is required for candidate face registration and verification
