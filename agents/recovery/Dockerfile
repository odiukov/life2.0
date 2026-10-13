FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /repo
COPY . .
RUN uv sync --frozen --no-dev --package agent-recovery

ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
RUN cp -r /repo/agents/recovery/app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
