#!/usr/bin/env bash
set -Eeuo pipefail

# Configura los backups externos cifrados (Restic) hacia un backend S3
# compatible (Backblaze B2). Ejecutar como root en el servidor.
#
# Pide de forma interactiva: bucket, endpoint, keyID y applicationKey
# (la applicationKey se oculta). Genera la contrasena de cifrado de Restic
# y la muestra UNA sola vez para guardarla fuera del servidor.
#
# No regenera la contrasena de cifrado si ya existe, para no perder el acceso
# a backups previos.

APP_ROOT="${APP_ROOT:-/srv/vapes-shop}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/compose.production.env}"
APP_GROUP="${APP_GROUP:-vapes-shop}"
SECRETS="$APP_ROOT/secrets"

[[ "${EUID}" -eq 0 ]] || { echo "ERROR: ejecuta como root." >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "ERROR: no existe $ENV_FILE" >&2; exit 1; }

read -rp "Bucket B2: " BUCKET
read -rp "Endpoint S3 (ej. s3.us-west-004.backblazeb2.com): " ENDPOINT
read -rp "keyID (Application Key ID): " KEYID
read -rsp "applicationKey (se oculta): " APPKEY; echo

[[ -n "$BUCKET" && -n "$ENDPOINT" && -n "$KEYID" && -n "$APPKEY" ]] \
  || { echo "ERROR: faltan datos." >&2; exit 1; }

install -d -o "$APP_GROUP" -g "$APP_GROUP" -m 0700 "$SECRETS"

REPO_FILE="$SECRETS/restic-repository.txt"
PASS_FILE="$SECRETS/restic-password.txt"
BACKEND_FILE="$SECRETS/restic-backend.env"

if [[ -e "$PASS_FILE" ]]; then
  echo "Aviso: $PASS_FILE ya existe; se conserva la contrasena de cifrado actual."
else
  RESTIC_PASS="$(openssl rand -base64 48 | tr -d '\n=' | tr '/+' '_-')"
  printf '%s\n' "$RESTIC_PASS" > "$PASS_FILE"
  echo "==================================================================="
  echo "GUARDA ESTA CONTRASENA DE CIFRADO DE BACKUPS FUERA DEL SERVIDOR:"
  echo
  echo "    $RESTIC_PASS"
  echo
  echo "Sin ella NO podras restaurar los backups si pierdes el servidor."
  echo "==================================================================="
fi

# Repositorio Restic (S3 de Backblaze) y credenciales del backend.
printf 's3:https://%s/%s\n' "$ENDPOINT" "$BUCKET" > "$REPO_FILE"
printf 'AWS_ACCESS_KEY_ID=%s\nAWS_SECRET_ACCESS_KEY=%s\n' "$KEYID" "$APPKEY" \
  > "$BACKEND_FILE"

# Permisos:
#  - repo y password los lee el contenedor (root con cap_drop ALL) por montaje,
#    asi que deben pertenecer a root para que su bit de lectura de propietario
#    baste sin CAP_DAC_OVERRIDE.
#  - backend.env lo lee "docker compose" en el host (root o vapes-shop).
chown root:root "$REPO_FILE" "$PASS_FILE"
chmod 0600 "$REPO_FILE" "$PASS_FILE"
chown root:"$APP_GROUP" "$BACKEND_FILE"
chmod 0640 "$BACKEND_FILE"

set_kv() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

set_kv EXTERNAL_BACKUP_ENABLED true
set_kv BACKUP_REQUIRE_EXTERNAL true
set_kv EXTERNAL_BACKUP_HOST vapeshopcol
set_kv EXTERNAL_BACKUP_CHECK_SUBSET 100%

echo "OK: secretos escritos y entorno actualizado."
echo "Repositorio: s3:https://${ENDPOINT}/${BUCKET}"
echo "Siguiente: inicializar el repositorio y hacer el primer backup."
