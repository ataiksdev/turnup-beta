FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --system --create-home app && mkdir -p data/uploads data/kyc && chown -R app:app /app
USER app
EXPOSE 8000
# Single-process default (migrates on startup, runs jobs in-process). docker-compose.yml
# overrides this to split migrate / API / worker roles.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
