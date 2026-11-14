# One image: FastAPI serves /api/* and the built SPA (D-102).

# --- 1. Build the web app ---
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. Python runtime ---
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    APP_ENV=prod \
    STATIC_DIR=/app/frontend/dist \
    PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-dev
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000
# Migrations run on start (single instance on Render). --proxy-headers makes
# request.client the real visitor behind Render's proxy (login rate limit per IP).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
