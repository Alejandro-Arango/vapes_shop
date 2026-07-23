#!/usr/bin/env bash
set -Eeuo pipefail

# Genera compose.production.env con secretos aleatorios creados en el host.
# No sobrescribe un archivo existente para no invalidar la contrasena de MySQL
# ya usada por el volumen de datos. Para regenerar, borra el archivo a mano.
#
# Variables opcionales:
#   ENV_PATH        destino (default /srv/vapes-shop/compose.production.env)
#   DOMAIN          dominio raiz (default vapeshopcol.com)
#   ADMIN_IP        IP con acceso al panel admin (requerido)
#   ENV_OWNER       propietario del archivo (default vapes-shop:vapes-shop)
#
# El correo se configura en modo consola (los mensajes quedan en el log, no se
# envian) hasta conectar un SMTP real. Cambia DJANGO_EMAIL_* despues.

ENV_PATH="${ENV_PATH:-/srv/vapes-shop/compose.production.env}"
DOMAIN="${DOMAIN:-vapeshopcol.com}"
ADMIN_IP="${ADMIN_IP:?Define ADMIN_IP con la IP publica que administrara el panel}"
ENV_OWNER="${ENV_OWNER:-vapes-shop:vapes-shop}"

if [[ -e "${ENV_PATH}" ]]; then
  echo "ERROR: ${ENV_PATH} ya existe; no se sobrescribe. Borralo si quieres regenerarlo." >&2
  exit 1
fi

gen_secret() {
  openssl rand -base64 "${1:-36}" | tr -d '\n=' | tr '/+' '_-'
}

SECRET_KEY="$(gen_secret 48)"
DB_PASSWORD="$(gen_secret 36)"
DB_ROOT_PASSWORD="$(gen_secret 36)"

umask 077
cat >"${ENV_PATH}" <<EOF
APP_PORT=8080
APP_BIND_ADDRESS=127.0.0.1
APP_IMAGE=vapes-shop-web:local
BACKUP_IMAGE=vapes-shop-backup:local

DJANGO_DEBUG=False
DJANGO_SECRET_KEY=${SECRET_KEY}
DJANGO_ALLOWED_HOSTS=${DOMAIN},www.${DOMAIN}
DJANGO_CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://www.${DOMAIN}
DJANGO_ADMIN_URL_PATH=panel-seguro/
DJANGO_ADMIN_ALLOWED_IPS=${ADMIN_IP}
DJANGO_OTP_TOTP_ISSUER=Vape Shop Admin
DJANGO_PASSWORD_MIN_LENGTH=12
DJANGO_SESSION_COOKIE_AGE=604800
DJANGO_PASSWORD_RESET_TIMEOUT=3600
DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE=1048576
DJANGO_FILE_UPLOAD_MAX_MEMORY_SIZE=1048576
DJANGO_DATA_UPLOAD_MAX_NUMBER_FIELDS=1000
DJANGO_DATA_UPLOAD_MAX_NUMBER_FILES=20
AUTH_THROTTLE_RATE=20/min
AUTH_USER_THROTTLE_RATE=10/min
CONTACT_THROTTLE_RATE=10/hour
CART_THROTTLE_RATE=60/min
CHECKOUT_THROTTLE_RATE=20/min
DJANGO_SESSION_COOKIE_SECURE=True
DJANGO_CSRF_COOKIE_SECURE=True
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True
DJANGO_SECURE_REFERRER_POLICY=same-origin
DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY=same-origin
DJANGO_CROSS_ORIGIN_RESOURCE_POLICY=same-origin
DJANGO_PERMISSIONS_POLICY=camera=(), microphone=(), geolocation=(), payment=(), usb=()
DJANGO_CONTENT_SECURITY_POLICY="default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; media-src 'self'; worker-src 'self'"
DJANGO_USE_X_FORWARDED_PROTO=True
DJANGO_TRUST_X_FORWARDED_FOR=True
DJANGO_LOG_FORMAT=json
DJANGO_STORE_LOG_LEVEL=WARNING
DJANGO_REQUEST_LOG_LEVEL=WARNING
GUNICORN_WORKERS=3
GUNICORN_THREADS=2
GUNICORN_TIMEOUT=60

DB_MEMORY_LIMIT=1536m
DB_CPU_LIMIT=1.50
WEB_MEMORY_LIMIT=768m
WEB_CPU_LIMIT=1.00
PROXY_MEMORY_LIMIT=128m
PROXY_CPU_LIMIT=0.25
CADDY_MEMORY_LIMIT=128m
CADDY_CPU_LIMIT=0.25

DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DJANGO_EMAIL_HOST=localhost
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_HOST_USER=no-reply@${DOMAIN}
DJANGO_EMAIL_HOST_PASSWORD=$(gen_secret 24)
DJANGO_EMAIL_USE_TLS=True
DJANGO_EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL="Vape Shop <no-reply@${DOMAIN}>"
CONTACT_NOTIFICATION_EMAIL=contacto@${DOMAIN}
ORDER_NOTIFICATION_EMAIL=pedidos@${DOMAIN}
INVENTORY_NOTIFICATION_EMAIL=inventario@${DOMAIN}

MYSQL_DATABASE=vapes_shop
MYSQL_USER=vapes_user
MYSQL_PASSWORD=${DB_PASSWORD}
MYSQL_ROOT_PASSWORD=${DB_ROOT_PASSWORD}
DJANGO_DB_CONN_MAX_AGE=60
DJANGO_DB_CONNECT_TIMEOUT=10

BACKUP_PATH=/srv/vapes-shop/backups
BACKUP_RETENTION_DAYS=14
EXTERNAL_BACKUP_ENABLED=false
BACKUP_REQUIRE_EXTERNAL=false

CONTACT_WHATSAPP_NUMBER=573042914452
EOF

chmod 600 "${ENV_PATH}"
chown "${ENV_OWNER}" "${ENV_PATH}" 2>/dev/null || true

echo "OK: ${ENV_PATH} generado (modo correo=consola temporal, admin IP=${ADMIN_IP})."
