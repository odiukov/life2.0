FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY agents/workout/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

COPY agents/workout/app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
