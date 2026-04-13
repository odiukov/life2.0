FROM python:3.12-slim

WORKDIR /app

# Install claude CLI
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://claude.ai/install.sh | sh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
