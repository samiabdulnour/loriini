# The licence service (D125; docs/licence-service.md): Python's standard
# library and the licence modules, nothing else -- no numpy, no pip install.
#
# Built from the repository's root, where .dockerignore lets in src/ alone:
#
#   fly deploy . --config deploy/licence-service/fly.toml \
#       --dockerfile deploy/licence-service/Dockerfile --ha=false
#
# It runs as root inside its container because the host mounts the volume
# that holds the database as root; the container holds nothing else.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    LORIINI_DATABASE=/data/licences.sqlite3

WORKDIR /app
COPY src/sun_study /app/sun_study

EXPOSE 8080
CMD ["python", "-m", "sun_study.licence_service", "serve"]
