# Operacion programada de backups

Esta guia define la ejecucion automatica y los simulacros de recuperacion del
despliegue. No depende del dominio publico, pero requiere Docker, systemd, las
imagenes productivas y el repositorio Restic inicializado.

## Objetivos

- RPO de datos: maximo 26 horas desde el ultimo backup local saludable.
- RTO de datos: maximo 900 segundos para comprobar el repositorio Restic,
  restaurar el ultimo snapshot y validar su integridad.

El RTO medido aqui cubre recuperacion de datos. El RTO completo del servicio
tambien incluye aprovisionar infraestructura, restaurar MySQL, iniciar la
aplicacion y validar checkout; debe medirse posteriormente en staging.

## Operaciones

`scripts/backup_operations.py cycle`:

1. adquiere el mismo lock usado por despliegues y rollbacks;
2. valida Compose y garantiza que MySQL este saludable;
3. crea el backup local;
4. valida antiguedad, checksums, archivos y espacio;
5. crea la copia Restic externa;
6. ejecuta `restic check`, restaura y compara el snapshot;
7. registra RPO y duracion total.

`scripts/backup_operations.py drill`:

1. adquiere el lock de despliegue;
2. valida el ultimo backup local;
3. restaura y verifica el ultimo snapshot externo;
4. exige que el identificador externo coincida con el local;
5. falla si incumple RPO o RTO.

Los fallos pueden notificarse mediante `MONITOR_WEBHOOK_URL` y
`MONITOR_WEBHOOK_TOKEN`.

## Programacion

Las unidades de `ops/systemd/` asumen:

- repositorio en `/srv/vapes-shop`;
- usuario de servicio `vapes-shop`;
- acceso al grupo `docker`;
- entorno productivo en `/srv/vapes-shop/compose.production.env`;
- estado de despliegue en `/srv/vapes-shop/.deploy/current.json`.

Si las rutas son distintas, deben ajustarse antes de instalar.

```bash
sudo install -d -m 0750 /etc/vapes-shop
sudo install -m 0640 \
  ops/systemd/backup-operations.env.example \
  /etc/vapes-shop/backup-operations.env
sudo install -m 0644 \
  ops/systemd/vapes-shop-backup.service \
  ops/systemd/vapes-shop-backup.timer \
  ops/systemd/vapes-shop-recovery-drill.service \
  ops/systemd/vapes-shop-recovery-drill.timer \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
  vapes-shop-backup.timer \
  vapes-shop-recovery-drill.timer
```

El backup se programa diariamente a las 02:15 y el simulacro los domingos a
las 04:00, ambos en `America/Bogota`. Los timers son persistentes: si el host
estaba apagado, systemd ejecuta la tarea pendiente al volver.

## Verificacion

```bash
systemctl list-timers 'vapes-shop-*'
sudo systemctl start vapes-shop-backup.service
sudo systemctl start vapes-shop-recovery-drill.service
journalctl -u vapes-shop-backup.service -u vapes-shop-recovery-drill.service
sudo cat /var/lib/vapes-shop/backup-cycle.json
sudo cat /var/lib/vapes-shop/recovery-drill.json
```

Cada reporte se escribe atomicamente y con `UMask=0077`. Un resultado
`critical`, una unidad fallida o la ausencia de un reporte reciente debe
generar una investigacion operativa.

## Cambios de objetivos

Los valores se sobrescriben en
`/etc/vapes-shop/backup-operations.env`:

```text
BACKUP_REQUIRE_EXTERNAL=true
BACKUP_RPO_HOURS=26
BACKUP_RTO_SECONDS=900
BACKUP_OPERATION_TIMEOUT=7200
BACKUP_ALERT_TIMEOUT=10
```

Un objetivo solo debe ampliarse con una decision documentada de negocio. La
retencion, frecuencia, RPO y RTO deben ser coherentes entre si.
