# Stage 1: Build minified Tailwind CSS v4 bundle
FROM node:24-slim AS css-builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY static/css/input.css ./static/css/input.css
COPY static/js ./static/js
COPY templates ./templates
COPY support ./support
RUN npm run build

# Stage 2: Resolve & install Python dependencies with uv (including container extras)
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS python-builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra container

# Stage 3: Minimal non-root runtime image
FROM python:3.13-slim-bookworm AS runtime

RUN groupadd --system --gid 10001 appuser && \
    useradd --system --uid 10001 --gid appuser --no-create-home appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000

WORKDIR /app
COPY --from=python-builder /app/.venv /app/.venv
COPY . /app
COPY --from=css-builder /build/static/css/output.css /app/static/css/output.css

RUN sed -i 's/\r$//' /app/docker/entrypoint.sh && \
    chmod +x /app/docker/entrypoint.sh && \
    mkdir -p /app/staticfiles /app/uploads && \
    DJANGO_SECRET_KEY=docker-build-collectstatic-placeholder \
    USE_REMOTE_DB=False \
    python manage.py collectstatic --noinput && \
    chown -R appuser:appuser /app/staticfiles /app/uploads

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.getenv('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health/', timeout=4).read()"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "durrat_tarim.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
