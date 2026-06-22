# Recuperacion integral de produccion

Este procedimiento reconstruye MySQL, media, Django y Nginx desde el ultimo
snapshot Restic externo sobre un host Ubuntu ya aprovisionado. No requiere que
el dominio apunte al host nuevo: las pruebas finales se ejecutan localmente con
el `Host` productivo y `X-Forwarded-Proto: https`.

## Objetivo

El objetivo inicial de recuperacion del servicio es 1800 segundos desde que se
ejecuta el comando de recuperacion hasta que:

- el snapshot externo se materializa como backup local;
- MySQL y media quedan restaurados;
- las migraciones y roles operativos quedan aplicados;
- `/healthz` responde correctamente;
- el catalogo `/api/products/` devuelve JSON valido.

Este tiempo incluye descarga de imagenes, restauracion y arranque. No incluye
crear la VM, transferir el repositorio, recuperar secretos, actualizar DNS ni
emitir certificados TLS. El RTO de negocio completo debe medir tambien esas
actividades cuando exista proveedor y dominio.

## Prerrequisitos

- host limpio preparado con `docs/HOST_PROVISIONING.md`;
- repositorio en `/srv/vapes-shop`;
- `compose.production.env` con modo `0600`;
- credenciales Restic y secretos recuperados desde un gestor independiente;
- el mismo `EXTERNAL_BACKUP_HOST` usado para crear los snapshots;
- manifiesto de recuperacion y checksum de una release aprobada;
- `/srv/vapes-shop/backups` vacio;
- ausencia de `.deploy/current.json`;
- ningun contenedor ni volumen previo del proyecto.

La herramienta se niega a operar si detecta estado productivo o contenedores
activos. Para un incidente parcial debe utilizarse despliegue, rollback o la
restauracion manual documentada, no este flujo.

## Procedimiento

1. Auditar el host:

```bash
cd /srv/vapes-shop
sudo python3 scripts/check_host_readiness.py --mode bootstrap
```

2. Confirmar que las imágenes corresponden a una release aprobada y descargar
   el manifiesto atestiguado y su checksum:

```bash
gh release download v1.2.3 \
  --repo ORGANIZACION/REPOSITORIO \
  --pattern 'recovery-manifest.*'
gh attestation verify recovery-manifest.json \
  --repo ORGANIZACION/REPOSITORIO
python3 scripts/release_manifest.py verify \
  --manifest recovery-manifest.json \
  --checksum recovery-manifest.sha256 \
  --expected-repository ORGANIZACION/REPOSITORIO \
  --expected-tag v1.2.3
```

La atestacion confirma la procedencia en GitHub Actions; el checksum detecta
corrupcion y el verificador restringe repositorio, release, commit e imagenes.

3. Ejecutar como el usuario de servicio:

```bash
sudo -u vapes-shop python3 scripts/recover_production.py \
  --release-manifest recovery-manifest.json \
  --manifest-checksum recovery-manifest.sha256 \
  --expected-repository ORGANIZACION/REPOSITORIO \
  --expected-tag v1.2.3 \
  --confirm RECOVER-PRODUCTION-FROM-EXTERNAL-BACKUP \
  --output /var/lib/vapes-shop/disaster-recovery.json
```

El archivo de reporte y `.deploy/current.json` se escriben atomicamente con
modo `0600`. Si la recuperacion funciona pero supera el objetivo, el servicio
queda iniciado y el comando termina con error para registrar el incumplimiento.

4. Revisar:

```bash
sudo cat /var/lib/vapes-shop/disaster-recovery.json
sudo -u vapes-shop docker compose \
  --env-file compose.production.env \
  --file compose.yaml \
  --file compose.production.yaml \
  ps
curl --fail --header 'Host: DOMINIO_REAL' \
  --header 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8080/healthz
```

5. Habilitar los timers y ejecutar la auditoria productiva:

```bash
sudo systemctl enable --now \
  vapes-shop-backup.timer \
  vapes-shop-recovery-drill.timer
sudo python3 scripts/check_host_readiness.py --mode production
```

Solo despues deben actualizarse el balanceador, DNS o reglas publicas.

## Fallos

- No borrar `.deploy.lock` sin confirmar que no hay otra operacion activa.
- No vaciar un `BACKUP_PATH` existente para forzar este flujo.
- No usar etiquetas mutables como `latest`.
- No confiar en el manifiesto antes de verificar atestacion y checksum.
- No desactivar el backup externo obligatorio.
- Conservar el reporte, logs de Compose y tiempos del incidente.

Si falla despues de restaurar MySQL pero antes de publicar el estado, mantener
el host aislado y diagnosticar. El flujo no intenta un rollback automatico
porque parte de la perdida completa del servidor anterior.
