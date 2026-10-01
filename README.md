# Backend

FastAPI backend for AI Legal Document Simplifier.

## Requirements
Python 3.11+ and PostgreSQL 14+ are recommended.

## Setup
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Edit `.env` with your PostgreSQL credentials and optionally `GEMINI_API_KEY`.

Create the database with the root `database_setup.sql`, or create an empty `Ai_Legal` database and run:
```powershell
alembic upgrade head
```

Run:
```powershell
python -m uvicorn app.main:app --reload
```
Swagger: `http://localhost:8000/docs`
ReDoc: `http://localhost:8000/redoc`

## AI
The server starts without a Gemini API key. AI endpoints return HTTP 503 with a configuration error until `GEMINI_API_KEY` is configured. No fake AI responses are generated.

## Tests
```powershell
pytest
```
