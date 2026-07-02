#!/usr/bin/env bash

set -Eeuo pipefail

umask 077

readonly BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
readonly MEDIA_SOURCE="${MEDIA_SOURCE:-/source/media}"
readonly RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

fail() {
    echo "$1" >&2
    exit 1
}

require_variable() {
    local variable_name="$1"

    if [[ -z "${!variable_name:-}" ]]; then
        fail "Falta la variable obligatoria ${variable_name}."
    fi
}

validate_directory_target() {
    local path="$1"
    local label="$2"
    local parent

    parent="$(dirname -- "${path}")"

    if [[ -L "${path}" ]]; then
        fail "${label} no puede ser un enlace simbolico."
    fi

    if [[ -e "${path}" && ! -d "${path}" ]]; then
        fail "${label} debe ser un directorio regular."
    fi

    if [[ -L "${parent}" ]]; then
        fail "El directorio padre de ${label} no puede ser un enlace simbolico."
    fi
}

require_regular_directory() {
    local path="$1"
    local label="$2"

    if [[ -L "${path}" ]]; then
        fail "${label} no puede ser un enlace simbolico."
    fi

    if [[ ! -d "${path}" ]]; then
        fail "${label} debe ser un directorio regular."
    fi
}

for variable_name in MYSQL_HOST MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD; do
    require_variable "${variable_name}"
done

if [[ ! "${RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
    fail "BACKUP_RETENTION_DAYS debe ser un entero mayor o igual a cero."
fi

validate_directory_target "${BACKUP_ROOT}" "BACKUP_ROOT"
mkdir -p -- "${BACKUP_ROOT}"
require_regular_directory "${BACKUP_ROOT}" "BACKUP_ROOT"
require_regular_directory "${MEDIA_SOURCE}" "MEDIA_SOURCE"

if find "${MEDIA_SOURCE}" -type l -print -quit | grep -q .; then
    fail "El respaldo de media no permite enlaces simbolicos."
fi

export MYSQL_PWD="${MYSQL_PASSWORD}"

for attempt in {1..30}; do
    if mysqladmin ping \
        --host="${MYSQL_HOST}" \
        --port="${MYSQL_PORT:-3306}" \
        --user="${MYSQL_USER}" \
        --silent; then
        break
    fi

    if [[ "${attempt}" -eq 30 ]]; then
        echo "MySQL no estuvo disponible dentro del tiempo esperado." >&2
        exit 1
    fi

    sleep 2
done

while true; do
    backup_id="$(date -u +%Y%m%dT%H%M%SZ)"
    final_directory="${BACKUP_ROOT}/${backup_id}"

    if [[ ! -e "${final_directory}" && ! -L "${final_directory}" ]]; then
        break
    fi

    sleep 1
done

temporary_directory="${BACKUP_ROOT}/.partial-${backup_id}-$$"

cleanup() {
    rm -rf -- "${temporary_directory}"
}

trap cleanup EXIT

if [[ -e "${temporary_directory}" || -L "${temporary_directory}" ]]; then
    fail "El directorio temporal de respaldo ya existe."
fi

mkdir -- "${temporary_directory}"

echo "Creando respaldo ${backup_id}..."

mysqldump \
    --host="${MYSQL_HOST}" \
    --port="${MYSQL_PORT:-3306}" \
    --user="${MYSQL_USER}" \
    --single-transaction \
    --quick \
    --routines \
    --events \
    --triggers \
    --hex-blob \
    --default-character-set=utf8mb4 \
    --no-tablespaces \
    --set-gtid-purged=OFF \
    "${MYSQL_DATABASE}" \
    | gzip --best > "${temporary_directory}/database.sql.gz"

tar \
    --create \
    --gzip \
    --file="${temporary_directory}/media.tar.gz" \
    --directory="${MEDIA_SOURCE}" \
    .

cat > "${temporary_directory}/metadata.txt" <<EOF
backup_id=${backup_id}
created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
database=${MYSQL_DATABASE}
mysql_host=${MYSQL_HOST}
EOF

(
    cd "${temporary_directory}"
    sha256sum database.sql.gz media.tar.gz metadata.txt > manifest.sha256
)

mv -- "${temporary_directory}" "${final_directory}"
latest_temporary="${BACKUP_ROOT}/.latest.tmp"

if [[ -L "${latest_temporary}" ]]; then
    fail ".latest.tmp no puede ser un enlace simbolico."
fi

printf '%s\n' "${backup_id}" > "${latest_temporary}"
mv -- "${latest_temporary}" "${BACKUP_ROOT}/latest.txt"
trap - EXIT

if [[ "${RETENTION_DAYS}" -gt 0 ]]; then
    find "${BACKUP_ROOT}" \
        -mindepth 1 \
        -maxdepth 1 \
        -type d \
        -name '20??????T??????Z' \
        -mtime "+${RETENTION_DAYS}" \
        -exec rm -rf -- {} +
fi

echo "Respaldo completado: ${final_directory}"
