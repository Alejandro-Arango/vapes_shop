# syntax=docker/dockerfile:1.7

FROM python:3.13.14-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY backend/requirements.txt backend/requirements-production.txt ./

RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip \
    && /opt/venv/bin/python -m pip install -r requirements-production.txt


FROM python:3.13.14-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libmariadb3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app backend /app/backend
COPY --chown=app:app docker /app/docker

RUN chmod 0555 /app/docker/start.sh /app/docker/release.sh \
    && mkdir -p /app/backend/staticfiles /app/backend/media \
    && chown -R app:app /app/backend/staticfiles /app/backend/media

USER app
WORKDIR /app/backend

RUN DJANGO_DEBUG=True \
    DJANGO_SECRET_KEY=container-build-secret-only \
    python manage.py collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; response=urlopen('http://127.0.0.1:8000/api/health/', timeout=3); raise SystemExit(0 if response.status == 200 else 1)"

CMD ["/app/docker/start.sh"]
