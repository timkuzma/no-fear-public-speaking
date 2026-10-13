FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ARG REVISION=uncommitted
LABEL io.nfs.application="no-fear-stage" io.nfs.schema="1" org.opencontainers.image.revision=$REVISION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY server ./server
COPY public ./public
COPY scripts ./scripts
RUN useradd --system --uid 10001 pilot && mkdir /data && chown pilot:pilot /data
USER pilot
ENV DATA_DIR=/data APP_ENV=production
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/readiness', timeout=3)"
CMD ["python", "-m", "server.runtime"]
