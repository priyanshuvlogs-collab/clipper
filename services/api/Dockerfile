# Pro Clipper API. Build from the repository root:
#   docker build -f services/api/Dockerfile services/api
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/api
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Media, database and saved API keys live here — mount a volume on it.
ENV PRO_CLIPPER_DATA=/data
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
