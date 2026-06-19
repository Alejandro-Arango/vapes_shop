#!/bin/sh
set -eu

python manage.py wait_for_database
python manage.py migrate --noinput

if [ "${DJANGO_CACHE_BACKEND:-locmem}" = "database" ]; then
    python manage.py createcachetable
fi

python manage.py setup_store_roles --apply
