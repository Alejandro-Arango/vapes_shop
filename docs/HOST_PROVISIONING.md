# Aprovisionamiento del host productivo

Esta guia prepara un unico host Ubuntu para ejecutar Docker Compose, los
despliegues controlados y las tareas programadas. No requiere dominio. El
dominio y TLS se incorporan despues, sin exponer directamente el puerto 8080.

## Alcance

El bootstrap:

- admite Ubuntu 22.04 y 24.04 LTS de 64 bits;
- instala Docker Engine y Compose desde el repositorio oficial de Docker;
- instala GitHub CLI 2.95.0 desde su release oficial y valida su SHA-256;
- crea el usuario de sistema `vapes-shop`;
- crea directorios con permisos restrictivos;
- activa actualizaciones de seguridad sin reinicios automaticos;
- configura UFW con entrada denegada por defecto;
- instala, pero no activa, los timers de backup y recuperacion.

No modifica `sshd_config`, claves SSH, usuarios administrativos, DNS ni TLS.
Esos cambios pueden cortar el acceso y requieren conocer el proveedor y la
red administrativa.

El grupo `docker` equivale practicamente a acceso root. Solo el usuario de
servicio y administradores autorizados deben pertenecer a ese grupo.

GitHub CLI se usa para descargar y verificar atestaciones de los manifiestos
de release. El bootstrap fija version y checksums para `amd64` y `arm64`.

## Requisitos

- una VM limpia con Ubuntu soportado;
- acceso root por consola o SSH;
- al menos 2 CPU, 4 GiB RAM y almacenamiento separado o remoto para backups;
- este repositorio transferido desde una fuente confiable;
- una regla de red del proveedor que limite SSH a direcciones administrativas.

## Bootstrap

Revisa primero las variables. `PUBLIC_WEB=false` mantiene cerrados 80 y 443
mientras no exista dominio ni proxy TLS.

```bash
cd /ruta/temporal/vapes_shop
sudo env \
  SSH_PORT=22 \
  SSH_ALLOWED_CIDR=203.0.113.10/32 \
  PUBLIC_WEB=false \
  bash ops/provision/ubuntu-bootstrap.sh
```

Si `SSH_ALLOWED_CIDR` queda vacio, SSH se permite desde cualquier origen con
limitacion de intentos. Es preferible restringirlo tanto en UFW como en el
firewall del proveedor.

Si se ejecuta dentro de una sesion SSH, el bootstrap rechaza un `SSH_PORT`
distinto al puerto de esa sesion antes de activar UFW.

El script no elimina instalaciones existentes de `docker.io`. Si detecta una,
se detiene para exigir una migracion explicita antes de instalar Docker CE.

## Transferencia y secretos

Copia el repositorio sin incluir `.git`, entornos virtuales, archivos `.env`,
backups ni secretos. Despues:

```bash
sudo rsync -a \
  --exclude '.git/' \
  --exclude 'backend/.venv/' \
  --exclude 'compose.production.env' \
  --exclude '.deploy/' \
  --exclude 'backups/' \
  --exclude 'external-backups/' \
  --exclude 'secrets/' \
  ./ /srv/vapes-shop/
sudo chown -R vapes-shop:vapes-shop /srv/vapes-shop
sudo chmod 0750 /srv/vapes-shop
sudo chmod 0700 /srv/vapes-shop/secrets
```

Crea `/srv/vapes-shop/compose.production.env` a partir del ejemplo, reemplaza
todos los valores y aplica:

```bash
sudo chown vapes-shop:vapes-shop \
  /srv/vapes-shop/compose.production.env
sudo chmod 0600 /srv/vapes-shop/compose.production.env
```

En produccion, `APP_BIND_ADDRESS=127.0.0.1` impide que Docker publique Nginx
en todas las interfaces. El futuro proxy TLS del host accedera localmente a
`127.0.0.1:8080`.

Esta vinculacion es obligatoria aunque UFW este activo: los puertos publicados
por Docker se procesan mediante sus propias reglas de red y no deben protegerse
unicamente con el firewall del host.

Las actualizaciones automaticas cubren los repositorios oficiales de Ubuntu.
Docker CE procede de un repositorio externo y debe actualizarse durante una
ventana de mantenimiento, seguida de esta auditoria y una prueba de despliegue.

## Auditoria

Tras el bootstrap:

```bash
sudo python3 scripts/check_host_readiness.py \
  --mode bootstrap \
  --output /var/lib/vapes-shop/host-readiness.json
```

Despues del primer despliegue y de activar los timers:

```bash
sudo systemctl enable --now \
  vapes-shop-backup.timer \
  vapes-shop-recovery-drill.timer
sudo python3 scripts/check_host_readiness.py \
  --mode production \
  --output /var/lib/vapes-shop/host-readiness.json
```

El modo `production` tambien exige:

- `compose.production.env` con propietario y modo correctos;
- puerto de aplicacion limitado a loopback;
- backup externo obligatorio;
- estado de despliegue `.deploy/current.json`;
- timers operativos habilitados.

Un resultado `critical` bloquea la salida a produccion. El reporte no contiene
los valores de los secretos.

## Limites

Este bootstrap hace reproducible un host individual, pero no crea la VM ni el
almacenamiento externo. La siguiente capa debe declarar esos recursos con
infraestructura como codigo para el proveedor elegido y ejecutar un simulacro
completo en un host desechable.
