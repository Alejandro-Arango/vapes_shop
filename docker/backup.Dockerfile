# syntax=docker/dockerfile:1.7

FROM mysql:8.4.10

USER root

RUN microdnf install --assumeyes coreutils tar \
    && microdnf clean all

COPY --chmod=0555 docker/backup.sh docker/restore.sh /usr/local/bin/

RUN bash -n /usr/local/bin/backup.sh /usr/local/bin/restore.sh

ENTRYPOINT ["/bin/bash"]
