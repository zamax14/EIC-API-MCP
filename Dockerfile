FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev \
 && useradd --system --uid 10001 app && mkdir -p data && chown app data
USER app

EXPOSE 8000
CMD ["uvicorn", "eic.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", \
     "--limit-concurrency", "64", "--timeout-keep-alive", "5", "--proxy-headers", "--forwarded-allow-ips", "*"]
