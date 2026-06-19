#!/usr/bin/env bash

set -Eeuo pipefail

umask 077

readonly BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
readonly MEDIA_SOURCE="${MEDIA_SOURCE:-/source/media}"
readonly BACKUP_ID="${RESTORE_BACKUP_ID:-}"
readonly EXPECTED_CONFIRMATION="RESTORE-${BACKUP_ID}"
readonly SAFETY_BACKUP="${RESTORE_CREATE_SAFETY_BACKUP:-true}"
readonly MEDIA_UID="${MEDIA_UID:-10001}"
readonly MEDIA_GID="${MEDIA_GID:-10001}"

fail() {
    echo "$1" >&2
    exit 1
}

for variable_name in MYSQL_HOST MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD; do
    if [[ -z "${!variable_name:-}" ]]; then
        fail "Falta la variable obligatoria ${variable_name}."
    fi
done

if [[ ! "${BACKUP_ID}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
    fail "RESTORE_BACKUP_ID debe tener el formato UTC YYYYMMDDTHHMMSSZ."
fi

if [[ "${RESTORE_CONFIRM:-}" != "${EXPECTED_CONFIRMATION}" ]]; then
    fail "Restauracion cancelada. Define RESTORE_CONFIRM=${EXPECTED_CONFIRMATION}."
fi

if [[ "${SAFETY_BACKUP}" != "true" && "${SAFETY_BACKUP}" != "false" ]]; then
    fail "RESTORE_CREATE_SAFETY_BACKUP debe ser true o false."
fi

if [[ ! "${MEDIA_UID}" =~ ^[0-9]+$ || ! "${MEDIA_GID}" =~ ^[0-9]+$ ]]; then
    fail "MEDIA_UID y MEDIA_GID deben ser identificadores numericos."
fi

readonly BACKUP_DIRECTORY="${BACKUP_ROOT}/${BACKUP_ID}"

for required_file in database.sql.gz media.tar.gz metadata.txt manifest.sha256; do
    if [[ ! -f "${BACKUP_DIRECTORY}/${required_file}" ]]; then
        fail "El respaldo no contiene ${required_file}."
    fi
done

(
    cd "${BACKUP_DIRECTORY}"
    sha256sum --check manifest.sha256
)

if tar --list --gzip --file="${BACKUP_DIRECTORY}/media.tar.gz" \
    | grep --extended-regexp '(^/|(^|/)\.\.(/|$))' > /dev/null; then
    fail "El archivo de media contiene rutas no seguras."
fi

temporary_directory="$(mktemp -d)"
restore_work_directory=""
media_restore_started="false"
media_swap_completed="false"

cleanup() {
    local exit_code="$?"

    set +e
    rm -rf -- "${temporary_directory}"

    if [[ -n "${restore_work_directory}" && -d "${restore_work_directory}" ]]; then
        if [[ "${media_swap_completed}" != "true" ]]; then
            if [[ "${media_restore_started}" == "true" ]]; then
                find "${MEDIA_SOURCE}" \
                    -mindepth 1 \
                    -maxdepth 1 \
                    ! -path "${restore_work_directory}" \
                    -exec rm -rf -- {} +
            fi

            find "${restore_work_directory}/previous" \
                -mindepth 1 \
                -maxdepth 1 \
                -exec mv --target-directory="${MEDIA_SOURCE}" -- {} +
        fi

        rm -rf -- "${restore_work_directory}"
    fi

    trap - EXIT
    exit "${exit_code}"
}

trap cleanup EXIT
mkdir -p "${temporary_directory}/media"

tar \
    --extract \
    --gzip \
    --file="${BACKUP_DIRECTORY}/media.tar.gz" \
    --directory="${temporary_directory}/media" \
    --no-same-owner

if [[ "${SAFETY_BACKUP}" == "true" ]]; then
    echo "Creando respaldo de seguridad previo a la restauracion..."
    /usr/local/bin/backup.sh
fi

export MYSQL_PWD="${MYSQL_PASSWORD}"

echo "Restaurando base de datos desde ${BACKUP_ID}..."
gzip --decompress --stdout "${BACKUP_DIRECTORY}/database.sql.gz" \
    | mysql \
        --host="${MYSQL_HOST}" \
        --port="${MYSQL_PORT:-3306}" \
        --user="${MYSQL_USER}" \
        --default-character-set=utf8mb4 \
        "${MYSQL_DATABASE}"

restore_work_directory="${MEDIA_SOURCE}/.restore-${BACKUP_ID}-$$"
readonly previous_media="${restore_work_directory}/previous"
readonly staged_media="${restore_work_directory}/staged"

mkdir -p "${previous_media}" "${staged_media}"
cp --archive "${temporary_directory}/media/." "${staged_media}/"
chown --recursive "${MEDIA_UID}:${MEDIA_GID}" "${staged_media}"

echo "Restaurando archivos media..."

find "${MEDIA_SOURCE}" \
    -mindepth 1 \
    -maxdepth 1 \
    ! -path "${restore_work_directory}" \
    -exec mv --target-directory="${previous_media}" -- {} +

media_restore_started="true"

find "${staged_media}" \
    -mindepth 1 \
    -maxdepth 1 \
    -exec mv --target-directory="${MEDIA_SOURCE}" -- {} +

media_swap_completed="true"
rm -rf -- "${restore_work_directory}"
restore_work_directory=""

echo "Restauracion completada desde ${BACKUP_ID}."
