FROM python:3.12-slim

WORKDIR /app

COPY telegram_bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

COPY telegram_bot/app/ ./app/

CMD ["python", "-m", "app.main"]
