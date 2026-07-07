# syntax=docker/dockerfile:1.7

FROM mysql:8.4.10

ARG TARGETARCH
ARG RESTIC_VERSION=0.19.0
ARG RESTIC_SHA256_AMD64=13176fe6d89d4357947a2cd107218ab2873a5f9d8e1ac2d4cd1c8e07e6839c21
ARG RESTIC_SHA256_ARM64=e522ce6bf748d753fee8093e8ec59359972cf5b6bc65fc7c7cf38ae952351d91

USER root

# coreutils lo provee coreutils-single en la imagen base; instalarlo aparte
# rompe el depsolve por conflicto de version con el repo ol9. Se actualizan los
# paquetes de la base para incorporar los parches de seguridad publicados.
RUN microdnf update --assumeyes \
    && microdnf install --assumeyes bzip2 ca-certificates python3 tar \
    && microdnf clean all

COPY --chmod=0555 docker/backup.sh docker/restore.sh /usr/local/bin/
COPY --chmod=0555 scripts/monitor_backups.py scripts/external_backup.py /usr/local/lib/vapes-shop/

RUN set -eu; \
    case "${TARGETARCH}" in \
        amd64) restic_sha256="${RESTIC_SHA256_AMD64}" ;; \
        arm64) restic_sha256="${RESTIC_SHA256_ARM64}" ;; \
        *) echo "Arquitectura Restic no soportada: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    restic_archive="/tmp/restic_${RESTIC_VERSION}_linux_${TARGETARCH}.bz2"; \
    RESTIC_URL="https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic_${RESTIC_VERSION}_linux_${TARGETARCH}.bz2" \
    RESTIC_ARCHIVE="${restic_archive}" \
    python3 -c "import os, urllib.request; urllib.request.urlretrieve(os.environ['RESTIC_URL'], os.environ['RESTIC_ARCHIVE'])"; \
    echo "${restic_sha256}  ${restic_archive}" | sha256sum --check --strict; \
    bunzip2 "${restic_archive}"; \
    install --mode=0555 "${restic_archive%.bz2}" /usr/local/bin/restic; \
    restic version; \
    bash -n /usr/local/bin/backup.sh /usr/local/bin/restore.sh; \
    python3 -m py_compile \
        /usr/local/lib/vapes-shop/monitor_backups.py \
        /usr/local/lib/vapes-shop/external_backup.py

ENTRYPOINT ["/bin/bash"]
