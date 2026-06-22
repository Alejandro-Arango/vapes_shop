#!/usr/bin/env bash
set -Eeuo pipefail

# Prepara un host Ubuntu para ejecutar el despliegue productivo.
# Debe ejecutarse como root desde una copia confiable del repositorio.

APP_USER="${APP_USER:-vapes-shop}"
APP_GROUP="${APP_GROUP:-vapes-shop}"
APP_ROOT="${APP_ROOT:-/srv/vapes-shop}"
SSH_PORT="${SSH_PORT:-22}"
SSH_ALLOWED_CIDR="${SSH_ALLOWED_CIDR:-}"
PUBLIC_WEB="${PUBLIC_WEB:-false}"
GH_VERSION="${GH_VERSION:-2.95.0}"
GH_SHA256_AMD64="${GH_SHA256_AMD64:-25d1e4729e8808c9ed3d613e96ebd3f3e44446f2d368c89d878a71a36ddb3d8c}"
GH_SHA256_ARM64="${GH_SHA256_ARM64:-d41e0b3b6218e5741c8bb4db39b16e53a59e0e06299a8489bd38f623ef7ebaae}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
SYSTEMD_ROOT="${PROJECT_ROOT}/ops/systemd"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    fail "Ejecuta este script como root."
  fi
}

validate_input() {
  [[ "${APP_USER}" =~ ^[a-z_][a-z0-9_-]*$ ]] ||
    fail "APP_USER no es valido."
  [[ "${APP_GROUP}" =~ ^[a-z_][a-z0-9_-]*$ ]] ||
    fail "APP_GROUP no es valido."
  [[ "${APP_ROOT}" == /* && "${APP_ROOT}" != "/" ]] ||
    fail "APP_ROOT debe ser una ruta absoluta distinta de /."
  [[ "${SSH_PORT}" =~ ^[0-9]+$ ]] ||
    fail "SSH_PORT debe ser numerico."
  ((SSH_PORT >= 1 && SSH_PORT <= 65535)) ||
    fail "SSH_PORT debe estar entre 1 y 65535."
  [[ "${PUBLIC_WEB}" == "true" || "${PUBLIC_WEB}" == "false" ]] ||
    fail "PUBLIC_WEB debe ser true o false."

  if [[ -n "${SSH_CONNECTION:-}" ]]; then
    read -r _ _ _ connected_ssh_port <<<"${SSH_CONNECTION}"
    [[ "${SSH_PORT}" == "${connected_ssh_port}" ]] ||
      fail "SSH_PORT no coincide con el puerto de la sesion SSH actual."
  fi

  for unit in \
    vapes-shop-backup.service \
    vapes-shop-backup.timer \
    vapes-shop-recovery-drill.service \
    vapes-shop-recovery-drill.timer; do
    [[ -f "${SYSTEMD_ROOT}/${unit}" ]] ||
      fail "No existe ${SYSTEMD_ROOT}/${unit}."
  done
}

load_ubuntu_release() {
  [[ -r /etc/os-release ]] || fail "No existe /etc/os-release."
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] ||
    fail "Este bootstrap solo admite Ubuntu."

  case "${VERSION_ID:-}" in
    22.04 | 24.04) ;;
    *) fail "Ubuntu ${VERSION_ID:-desconocido} no esta soportado." ;;
  esac

  [[ -n "${VERSION_CODENAME:-}" ]] ||
    fail "No fue posible determinar VERSION_CODENAME."
}

install_base_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y \
    ca-certificates \
    curl \
    git \
    gnupg \
    python3 \
    tar \
    ufw \
    unattended-upgrades
}

install_docker() {
  if dpkg-query -W -f='${Status}' docker.io 2>/dev/null |
    grep -q "install ok installed"; then
    if ! dpkg-query -W -f='${Status}' docker-ce 2>/dev/null |
      grep -q "install ok installed"; then
      fail "docker.io entra en conflicto con Docker CE; migralo explicitamente."
    fi
  fi

  install -m 0755 -d /etc/apt/keyrings
  curl --fail --silent --show-error --location \
    https://download.docker.com/linux/ubuntu/gpg \
    --output /etc/apt/keyrings/docker.asc
  chmod 0644 /etc/apt/keyrings/docker.asc

  cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

  apt-get update
  apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
  systemctl enable --now docker.service
}

install_github_cli() {
  local architecture archive_architecture expected_sha256

  architecture="$(dpkg --print-architecture)"

  case "${architecture}" in
    amd64)
      archive_architecture="amd64"
      expected_sha256="${GH_SHA256_AMD64}"
      ;;
    arm64)
      archive_architecture="arm64"
      expected_sha256="${GH_SHA256_ARM64}"
      ;;
    *)
      fail "Arquitectura GitHub CLI no soportada: ${architecture}."
      ;;
  esac

  local archive_name="gh_${GH_VERSION}_linux_${archive_architecture}.tar.gz"
  local download_url="https://github.com/cli/cli/releases/download/v${GH_VERSION}/${archive_name}"
  local temporary_directory
  temporary_directory="$(mktemp -d)"
  trap "rm -rf -- '${temporary_directory}'" EXIT

  curl --fail --silent --show-error --location \
    "${download_url}" \
    --output "${temporary_directory}/${archive_name}"
  printf '%s  %s\n' \
    "${expected_sha256}" \
    "${temporary_directory}/${archive_name}" \
    | sha256sum --check --strict
  tar \
    --extract \
    --gzip \
    --file="${temporary_directory}/${archive_name}" \
    --directory="${temporary_directory}"
  install -m 0755 \
    "${temporary_directory}/gh_${GH_VERSION}_linux_${archive_architecture}/bin/gh" \
    /usr/local/bin/gh
  gh version
  rm -rf -- "${temporary_directory}"
  trap - EXIT
}

create_service_identity() {
  if ! getent group "${APP_GROUP}" >/dev/null; then
    groupadd --system "${APP_GROUP}"
  fi

  if ! id "${APP_USER}" >/dev/null 2>&1; then
    useradd \
      --system \
      --gid "${APP_GROUP}" \
      --home-dir "${APP_ROOT}" \
      --shell /usr/sbin/nologin \
      "${APP_USER}"
  fi

  usermod --append --groups docker "${APP_USER}"
}

create_directories() {
  install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0750 \
    "${APP_ROOT}" \
    "${APP_ROOT}/backups" \
    "${APP_ROOT}/external-backups" \
    "${APP_ROOT}/.deploy" \
    /var/lib/vapes-shop
  install -d -o "${APP_USER}" -g "${APP_GROUP}" -m 0700 \
    "${APP_ROOT}/secrets"
  install -d -o root -g "${APP_GROUP}" -m 0750 /etc/vapes-shop
}

configure_security_updates() {
  cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

  cat >/etc/apt/apt.conf.d/52vapes-shop-unattended-upgrades <<'EOF'
Unattended-Upgrade::Automatic-Reboot "false";
EOF

  systemctl enable --now apt-daily.timer apt-daily-upgrade.timer
}

configure_firewall() {
  ufw default deny incoming
  ufw default allow outgoing

  if [[ -n "${SSH_ALLOWED_CIDR}" ]]; then
    ufw limit proto tcp from "${SSH_ALLOWED_CIDR}" to any port "${SSH_PORT}"
  else
    ufw limit "${SSH_PORT}/tcp"
  fi

  if [[ "${PUBLIC_WEB}" == "true" ]]; then
    ufw allow 80/tcp
    ufw allow 443/tcp
  fi

  ufw --force enable
}

install_operational_units() {
  install -m 0644 \
    "${SYSTEMD_ROOT}/vapes-shop-backup.service" \
    "${SYSTEMD_ROOT}/vapes-shop-backup.timer" \
    "${SYSTEMD_ROOT}/vapes-shop-recovery-drill.service" \
    "${SYSTEMD_ROOT}/vapes-shop-recovery-drill.timer" \
    /etc/systemd/system/
  install -m 0640 -o root -g "${APP_GROUP}" \
    "${SYSTEMD_ROOT}/backup-operations.env.example" \
    /etc/vapes-shop/backup-operations.env.example
  systemctl daemon-reload
}

main() {
  require_root
  validate_input
  load_ubuntu_release
  install_base_packages
  install_docker
  install_github_cli
  create_service_identity
  create_directories
  configure_security_updates
  configure_firewall
  install_operational_units

  docker version --format '{{.Server.Version}}'
  docker compose version
  printf '%s\n' \
    "Host preparado. Copia el repositorio y los secretos en ${APP_ROOT}," \
    "crea compose.production.env con modo 0600 y ejecuta la auditoria."
}

main "$@"
