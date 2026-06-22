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
- checkout Git limpio del tag que se va a recuperar;
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

2. Confirmar que las imágenes corresponden a una release aprobada y preparar
   los assets verificados:

```bash
python3 scripts/fetch_release_manifest.py \
  --repository ORGANIZACION/REPOSITORIO \
  --release-tag v1.2.3 \
  --output-dir /srv/vapes-shop/recovery-assets/v1.2.3
```

El comando exige un directorio vacio, descarga únicamente los dos assets,
valida la atestacion de GitHub Actions, comprueba el checksum y restringe
repositorio, release, commit e imagenes. Elimina los archivos si cualquier
verificacion falla.

Para un repositorio privado, entrega `GH_TOKEN` temporalmente con permiso
minimo de lectura de contenidos. No guardes ese token en el servidor.

3. Alinear el checkout con la release:

```bash
sudo -u vapes-shop git -C /srv/vapes-shop fetch \
  --depth 1 origin tag v1.2.3
sudo -u vapes-shop git -C /srv/vapes-shop checkout \
  --detach FETCH_HEAD
sudo -u vapes-shop git -C /srv/vapes-shop status \
  --short --untracked-files=no
```

La recuperacion vuelve a comprobar que `HEAD` coincide con `source_commit` del
manifiesto y que no existen modificaciones rastreadas. Los secretos, backups y
assets ignorados no bloquean la comprobacion.

4. Ejecutar como el usuario de servicio:

```bash
sudo -u vapes-shop python3 scripts/recover_production.py \
  --release-manifest \
  recovery-assets/v1.2.3/recovery-manifest.json \
  --manifest-checksum \
  recovery-assets/v1.2.3/recovery-manifest.sha256 \
  --expected-repository ORGANIZACION/REPOSITORIO \
  --expected-tag v1.2.3 \
  --confirm RECOVER-PRODUCTION-FROM-EXTERNAL-BACKUP \
  --output /var/lib/vapes-shop/disaster-recovery.json
```

El archivo de reporte y `.deploy/current.json` se escriben atomicamente con
modo `0600`. Si la recuperacion funciona pero supera el objetivo, el servicio
queda iniciado y el comando termina con error para registrar el incumplimiento.
En la ruta normal ambos archivos registran `source_mode` como
`verified-manifest`. Cada ejecucion genera un `recovery_attempt_id` hexadecimal
que se conserva en el estado, el reporte y cualquier alerta relacionada.

5. Revisar:

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

6. Habilitar los timers y ejecutar la auditoria productiva:

```bash
sudo systemctl enable --now \
  vapes-shop-backup.timer \
  vapes-shop-recovery-drill.timer
sudo python3 scripts/check_host_readiness.py --mode production
```

Solo despues deben actualizarse el balanceador, DNS o reglas publicas.

## Excepcion break-glass

Si GitHub no permite obtener el manifiesto durante el incidente, pero el equipo
de respuesta conserva referencias por digest aprobadas por otro canal, se puede
usar la ruta manual:

```bash
sudo -u vapes-shop python3 scripts/recover_production.py \
  --app-image ghcr.io/ORGANIZACION/REPOSITORIO@sha256:DIGEST_APP \
  --backup-image ghcr.io/ORGANIZACION/REPOSITORIO-backup@sha256:DIGEST_OPS \
  --break-glass-confirm USE-MANUAL-RECOVERY-IMAGES \
  --break-glass-reason "GitHub no disponible; digests aprobados en INC-1234" \
  --confirm RECOVER-PRODUCTION-FROM-EXTERNAL-BACKUP \
  --output /var/lib/vapes-shop/disaster-recovery.json
```

Esta excepcion no verifica tag, commit ni checkout contra un manifiesto. El
motivo debe ocupar una sola linea de 12 a 200 caracteres y queda registrado
junto con `source_mode: manual-break-glass` en el reporte y el estado
productivo. Debe existir autorizacion humana y seguimiento posterior del
incidente. No usar esta ruta solo para ahorrar los pasos de verificacion.
El controlador rechaza combinaciones incoherentes: el modo de manifiesto exige
tag y commit validos, mientras que break-glass los prohibe y exige el motivo.
Una vez validada la fuente, los reportes de error también conservan el modo,
las referencias de imagen y la identidad de release o el motivo break-glass.
Los fallos anteriores a esa validacion no registran datos no confiables.
El `recovery_attempt_id` sí aparece desde el inicio y debe usarse para
correlacionar reporte, alerta, logs y seguimiento del incidente.

Durante la operacion, `.deploy/recovery-in-progress.json` registra de forma
atomica el intento, la procedencia y la ultima fase iniciada. Se elimina en
salidas controladas. Si el proceso o el host terminan abruptamente, el journal
y `.deploy.lock` permanecen y bloquean otro intento hasta preservar evidencia,
confirmar el estado de contenedores, volúmenes, MySQL y media, y decidir la
recuperacion segura. Los reportes de fallo controlado incluyen
`recovery_phase`.

## Fallos

- No borrar `.deploy.lock` sin confirmar que no hay otra operacion activa.
- No borrar `recovery-in-progress.json` antes de registrar su contenido.
- No vaciar un `BACKUP_PATH` existente para forzar este flujo.
- No usar etiquetas mutables como `latest`.
- No confiar en el manifiesto antes de verificar atestacion y checksum.
- No ejecutar desde una rama, commit distinto o checkout modificado.
- No usar `manual-break-glass` sin documentar la indisponibilidad y los digests.
- No desactivar el backup externo obligatorio.
- Conservar el reporte, logs de Compose y tiempos del incidente.

Si falla despues de restaurar MySQL pero antes de publicar el estado, mantener
el host aislado y diagnosticar. El flujo no intenta un rollback automatico
porque parte de la perdida completa del servidor anterior.
