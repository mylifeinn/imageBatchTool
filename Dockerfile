FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY app.py .
COPY templates templates/
COPY static static/

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/uploads /app/processed /app/downloads
RUN chmod -R 777 /app

EXPOSE 5000

CMD ["python", "app.py"]
