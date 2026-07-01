#!/bin/sh
set -eu

python manage.py wait_for_database

exec gunicorn mi_tienda.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --threads "${GUNICORN_THREADS:-2}" \
    --backlog "${GUNICORN_BACKLOG:-256}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-30}" \
    --keep-alive "${GUNICORN_KEEP_ALIVE:-5}" \
    --limit-request-line "${GUNICORN_LIMIT_REQUEST_LINE:-4094}" \
    --limit-request-fields "${GUNICORN_LIMIT_REQUEST_FIELDS:-100}" \
    --limit-request-field_size "${GUNICORN_LIMIT_REQUEST_FIELD_SIZE:-8190}" \
    --max-requests "${GUNICORN_MAX_REQUESTS:-1000}" \
    --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-100}" \
    --error-logfile -
