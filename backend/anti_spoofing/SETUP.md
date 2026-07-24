# Anti-Spoofing API Setup

This guide sets up the anti-spoofing service only.

## 1. Requirements

Install these first:

- Python `3.10` only
- FFmpeg on your system `PATH`
- local model files under `backend/models/`
- Microsoft C++ Build Tools on Windows

Optional:

- Redis

Important:

- Python `3.10` is the only supported version.
- FFmpeg is required.

Quick check:

```powershell
python --version
ffmpeg -version
```

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

## 4. Configure Anti-Spoofing Settings

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

## 5. Verify Model Assets

These must exist:

- `backend/models/anti-spoof-mn3.onnx`
- `backend/models/buffalo_l`
- `backend/models/mms-300m-anti-deepfake`
- `backend/models/faster-whisper-large-v3-turbo`

## 6. Run the Service

From the repository root:

```powershell
cd backend\anti_spoofing
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Useful URLs:

- `http://127.0.0.1:8080/docs`
- `http://127.0.0.1:8080/health`
- `http://127.0.0.1:8080/ready`

## 7. Run Tests

```powershell
cd backend\anti_spoofing
..\.venv\Scripts\python.exe -m pytest -q
```

## 8. Troubleshooting

### `ready` is degraded

Check the model files and session store configuration.

### FFmpeg errors

Confirm:

```powershell
ffmpeg -version
```

### Wrong Python version

Recreate `backend/.venv` with Python `3.10`.
