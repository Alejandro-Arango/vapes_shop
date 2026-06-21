# Respuesta ante incidentes

Esta guia cubre incidentes operativos y de seguridad del despliegue de Vape
Shop. No sustituye las obligaciones legales ni los procedimientos del
proveedor de hosting.

## Severidad

- `SEV-1`: sitio caido, checkout indisponible, posible filtracion o perdida de
  datos.
- `SEV-2`: degradacion parcial, errores frecuentes, correo o admin
  indisponibles sin afectar compras ya confirmadas.
- `SEV-3`: fallo menor sin impacto directo para clientes.

## Primeros 15 minutos

1. Registrar hora UTC, persona responsable y sintomas.
2. Evitar despliegues y cambios no relacionados.
3. Guardar el `X-Request-ID`, URL, codigo HTTP y hora de los errores.
4. Revisar estado y logs:

   ```powershell
   docker compose --env-file compose.env ps
   docker compose --env-file compose.env logs --since 30m web proxy db
   curl.exe -i https://DOMINIO_REAL/livez
   curl.exe -i https://DOMINIO_REAL/healthz
   ```

5. Determinar el alcance: liveness, readiness, base de datos, cache, proxy,
   correo, checkout o seguridad.
6. Si existe riesgo de corrupcion o acceso no autorizado, detener escrituras:

   ```powershell
   docker compose --env-file compose.env stop proxy web
   ```

## Diagnostico rapido

### `/livez` falla

- Revisar el contenedor `proxy`, puertos, TLS y recursos del host.
- Si Nginx responde pero `/api/live/` falla, revisar `web` y Gunicorn.
- No reiniciar repetidamente sin conservar primero los logs.

### `/livez` funciona y `/healthz` falla

- Revisar `web`, `db` y la tabla de cache.
- Buscar el `request_id` de la alerta en logs de `proxy` y `web`.
- Confirmar espacio en disco, memoria, conexiones y estado de MySQL.

### El monitor de backups falla

- Detener despliegues y restauraciones hasta conocer la causa.
- Ejecutar `docker compose --env-file compose.env run --rm backup-monitor`.
- Si falla el checksum o un archivo comprimido, conservar el respaldo como
  evidencia y seleccionar una copia anterior verificada.
- Si falla por antiguedad, revisar el programador y crear un respaldo nuevo.
- Si falla por espacio, no borrar la ultima copia saludable; ampliar o liberar
  almacenamiento siguiendo la retencion documentada.

### Checkout falla

- No recrear pedidos manualmente hasta revisar la clave de idempotencia.
- Buscar eventos `checkout_failed` y el `request_id` relacionado.
- Confirmar stock, cupones, restricciones de base de datos y estado del correo.

### Posible incidente de seguridad

- Revocar credenciales afectadas y rotar secretos desde el proveedor.
- Invalidar sesiones administrativas y revisar MFA.
- Preservar logs y respaldos; no borrar evidencia.
- Revisar accesos administrativos, `EventLog` y cambios de datos.
- Evaluar obligaciones de notificacion antes de comunicar detalles.

## Mitigacion y recuperacion

Priorizar cambios reversibles:

1. Retirar trafico del servicio afectado.
2. Corregir configuracion o volver a la imagen estable anterior:

   ```powershell
   python .\scripts\deploy_production.py --rollback
   ```

3. Ejecutar migraciones solo si corresponden al codigo desplegado.
4. Restaurar datos unicamente si se confirma corrupcion o perdida.

La restauracion debe seguir la seccion `Backups y recuperacion` del README.
Siempre conservar el respaldo de seguridad previo y documentar el identificador
UTC restaurado.

## Verificacion posterior

Antes de reabrir trafico:

```powershell
curl.exe -i https://DOMINIO_REAL/livez
curl.exe -i https://DOMINIO_REAL/healthz
docker compose --env-file compose.env ps
docker compose --env-file compose.env logs --since 10m web proxy db
```

Comprobar además login, catalogo, carrito y un checkout controlado sin repetir
transacciones reales.

## Cierre

Registrar:

- inicio, deteccion, mitigacion y cierre en UTC;
- impacto y usuarios afectados;
- causa raiz y factores contribuyentes;
- comandos y cambios ejecutados;
- respaldo o version restaurada;
- acciones preventivas con responsable y fecha.

Los secretos, datos personales y tokens nunca deben copiarse al informe.
