FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

# i18n bundles: shared.i18n resolves locales via parents[2] of /shared/shared/i18n.py → /
COPY packages/i18n/locales/ /packages/i18n/locales/

COPY orchestrator/app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
