# Dependencies baked in, so running the tests does not reinstall ~100MB of
# packages every time. Rebuild only when requirements change:
#
#   docker build -t triage-dev -f dev.Dockerfile .
#
# Then (from the repo root, with a .env holding APP_DATABASE_URL etc.):
#
#   docker run --rm --env-file .env -v "$PWD:/app" -w /app triage-dev \
#     sh -c "ruff check . && pytest -q"
#
# Source is mounted rather than copied, so edits apply without rebuilding.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
