#!/usr/bin/env bash
set -Eeuo pipefail

# Configura las variables de correo SMTP en compose.production.env de forma
# interactiva, sin exponer la clave. Pensado para ejecutarse en el servidor.
#
# Variables opcionales:
#   ENV_PATH       destino (default /srv/vapes-shop/compose.production.env)
#   NOTIFY_EMAIL   correo que recibe contacto/pedidos/inventario
#   SMTP_HOST      host SMTP (default smtp-relay.brevo.com)
#   SMTP_PORT      puerto (default 587)

ENV_PATH="${ENV_PATH:-/srv/vapes-shop/compose.production.env}"
NOTIFY_EMAIL="${NOTIFY_EMAIL:-vapeshop.co@outlook.es}"
SMTP_HOST="${SMTP_HOST:-smtp-relay.brevo.com}"
SMTP_PORT="${SMTP_PORT:-587}"

if [[ ! -f "${ENV_PATH}" ]]; then
  echo "ERROR: no existe ${ENV_PATH}" >&2
  exit 1
fi

read -rp "SMTP login (usuario que muestra Brevo): " SMTP_LOGIN
read -rsp "SMTP key (se oculta al pegar): " SMTP_KEY
echo

if [[ -z "${SMTP_LOGIN}" || -z "${SMTP_KEY}" ]]; then
  echo "ERROR: el login y la clave son obligatorios." >&2
  exit 1
fi

# Elimina cualquier definicion previa de estas claves para no duplicarlas.
sed -i -E '/^(DJANGO_EMAIL_BACKEND|DJANGO_EMAIL_HOST|DJANGO_EMAIL_PORT|DJANGO_EMAIL_USE_TLS|DJANGO_EMAIL_USE_SSL|DJANGO_EMAIL_HOST_USER|DJANGO_EMAIL_HOST_PASSWORD|CONTACT_NOTIFICATION_EMAIL|ORDER_NOTIFICATION_EMAIL|INVENTORY_NOTIFICATION_EMAIL)=/d' "${ENV_PATH}"

{
  printf 'DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend\n'
  printf 'DJANGO_EMAIL_HOST=%s\n' "${SMTP_HOST}"
  printf 'DJANGO_EMAIL_PORT=%s\n' "${SMTP_PORT}"
  printf 'DJANGO_EMAIL_USE_TLS=True\n'
  printf 'DJANGO_EMAIL_USE_SSL=False\n'
  printf 'DJANGO_EMAIL_HOST_USER=%s\n' "${SMTP_LOGIN}"
  printf 'DJANGO_EMAIL_HOST_PASSWORD=%s\n' "${SMTP_KEY}"
  printf 'CONTACT_NOTIFICATION_EMAIL=%s\n' "${NOTIFY_EMAIL}"
  printf 'ORDER_NOTIFICATION_EMAIL=%s\n' "${NOTIFY_EMAIL}"
  printf 'INVENTORY_NOTIFICATION_EMAIL=%s\n' "${NOTIFY_EMAIL}"
} >>"${ENV_PATH}"

chmod 600 "${ENV_PATH}"
chown vapes-shop:vapes-shop "${ENV_PATH}" 2>/dev/null || true

echo "SMTP escrito. Recreando el contenedor web..."
docker compose --env-file "${ENV_PATH}" \
  -f compose.yaml -f compose.production.yaml -f compose.tls.yaml \
  up -d web

echo "EMAIL_CONFIGURADO"
