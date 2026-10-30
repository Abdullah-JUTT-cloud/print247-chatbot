# API container: Python + FastAPI only. Mongo and Qdrant are separate
# containers (see docker-compose.yml) — this image never bundles a database.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY kb ./kb
COPY scripts ./scripts
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
