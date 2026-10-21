# TrustVault backend

FastAPI + Python scaffold. Only `GET /health` is implemented.

Authentication, documents, grants, R2 storage, and database models are not wired yet.

## Setup

```bash
cd backend
py -3.12 -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Tests

```bash
pytest -v
```
