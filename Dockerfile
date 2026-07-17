FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY api.py .

ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
