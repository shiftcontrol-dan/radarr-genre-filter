FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml requirements.txt README.md ./
COPY radarr_janitor ./radarr_janitor
RUN pip install --no-cache-dir -e ".[web]"

ENV WEB_HOST=0.0.0.0 \
    WEB_PORT=5056 \
    JANITOR_DB=/data/janitor.db
EXPOSE 5056
VOLUME ["/data"]

CMD ["python", "-m", "radarr_janitor.webapp"]
