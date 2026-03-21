# BrainAPI

## Project Overview
BrainAPI is a SaaS-ready FastAPI backend starter kit that acts as a unified AI gateway and automation platform. It provides a REST API for AI text generation, image generation, speech transcription, automation workflows, and SaaS controls (API key management, billing, rate limiting).

## Architecture
- **Framework**: FastAPI (Python 3.12) with Uvicorn ASGI server
- **Database**: SQLite (default/dev) or PostgreSQL (production)
- **Cache/Rate Limiting**: Redis (optional, falls back to in-memory)
- **AI Providers**: OpenAI, Anthropic, Groq, Gemini, Together, Ollama, Pollinations
- **Payments**: Razorpay integration
- **Email**: SMTP-based transactional emails
- **Frontend**: Static HTML/JS served via FastAPI's StaticFiles at `/ui`, homepage at `/`

## Project Structure
```
app/
  main.py          # FastAPI app entry point, all route definitions
  config.py        # Pydantic-Settings configuration (reads from .env)
  db.py            # SQLAlchemy engine and session, init_db()
  models.py        # SQLAlchemy database models
  schemas.py       # Pydantic request/response models
  auth.py          # Authentication and API key management
  billing.py       # Razorpay payment integration
  emails.py        # Email queuing and dispatching
  metering.py      # Usage event tracking
  security.py      # Rate limiting middleware
  services.py      # Automation workflow execution
  ai_gateway/      # Unified AI provider gateway
  static/          # Frontend HTML/CSS/JS files
tests/             # Pytest test suite
brainapi.config.json  # AI gateway routing configuration
requirements.txt   # Python dependencies
```

## Key Configuration
- Config is managed via `.env` file (see `.env.example`)
- Default database: SQLite at `./brainapi.db` (no external DB needed in dev)
- Redis is optional - rate limiting falls back to in-memory without it
- Set `PROVIDER` env var to choose AI provider (default: `auto` tries multiple)
- `AUTO_CREATE_TABLES=true` creates DB tables on startup

## Running
- **Dev**: `uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload`
- **Production**: `gunicorn --bind 0.0.0.0:5000 --reuse-port -k uvicorn.workers.UvicornWorker app.main:app`

## API Access
- Public routes: `/`, `/health`, `/docs`, `/redoc`, `/api/v1/auth/*`, `/api/v1/public/*`
- Protected routes require `X-API-Key` header or `Authorization: Bearer <key>`
- Admin routes require `X-Admin-Key` header with `ADMIN_API_KEY` value

## Dependencies
fastapi, uvicorn, pydantic, pydantic-settings, httpx, openai, python-multipart, sqlalchemy, psycopg[binary], redis, Pillow, pytest, gunicorn
