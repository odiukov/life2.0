FROM python:3.12-slim
WORKDIR /app

COPY sync_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library (needed for shared.telemetry)
COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

COPY sync_service/app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
