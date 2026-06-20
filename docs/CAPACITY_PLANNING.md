# Capacidad y rendimiento

Esta guia define una linea base reproducible. No certifica capacidad
productiva: los resultados dependen del proveedor, red, almacenamiento,
base de datos, volumen de datos y trafico real.

## Alcance actual

La prueba `performance/catalog.js` cubre lectura anonima:

- pagina principal;
- categorias;
- catalogo paginado con 24 productos;
- liveness y readiness.

La prueba `performance/checkout.js` cubre escritura autenticada sobre MySQL:

- sesiones independientes con carrito preparado;
- compradores concurrentes compitiendo por inventario limitado;
- bloqueo de producto y rechazo controlado al agotarse el stock;
- reintento con la misma clave de idempotencia;
- consistencia entre ordenes, items, historial y movimientos de inventario.

La prueba `performance/coupon.js` enfrenta sesiones con productos distintos
contra un mismo cupon limitado. Al no compartir inventario, la serializacion
depende del bloqueo del cupon y permite detectar usos por encima de
`max_uses`.

Las sesiones y los productos se generan en una base dedicada cuyo nombre debe
incluir `performance`. La utilidad se niega a operar sin
`CHECKOUT_LOAD_TEST_ENABLED=true`, y el workflow elimina el archivo de sesiones
antes de publicar artefactos.

## Host de referencia inicial

La configuracion parte de un host con al menos 2 vCPU y 4 GB de RAM. Compose
aplica limites configurables:

| Servicio | Memoria | CPU | Procesos |
| --- | ---: | ---: | ---: |
| MySQL | 768 MB | 1.00 | 256 |
| Migraciones | 512 MB | 0.50 | 128 |
| Django/Gunicorn | 512 MB | 1.00 | 256 |
| Nginx | 128 MB | 0.25 | 128 |
| Backup | 512 MB | 0.50 | 128 |
| Restore | 512 MB | 0.50 | 128 |

Backup y restore usan el perfil `ops` y no deben ejecutarse simultaneamente
sin revisar la memoria disponible. Los valores se cambian en el archivo de
entorno, no editando Compose en cada servidor.

Gunicorn inicia con 3 workers y 2 threads: hasta 6 solicitudes pueden estar
en ejecucion al mismo tiempo dentro de Django. Eso no equivale a 6 solicitudes
por segundo. Una aproximacion util es:

```text
concurrencia necesaria = solicitudes por segundo x latencia en segundos
```

Con 5 solicitudes por segundo y p95 de 0.75 segundos, la demanda aproximada
es 3.75 solicitudes concurrentes. Debe conservarse margen para picos, tareas
de base de datos y respuestas lentas.

## Perfiles y umbrales

`smoke` usa 2 usuarios virtuales durante 20 segundos. Se ejecuta en pushes y
pull requests para detectar regresiones gruesas.

`baseline` sube gradualmente hasta 10 usuarios virtuales y se ejecuta cada
semana o manualmente. Sus resultados sirven para comparar commits bajo el
mismo entorno efimero, no para predecir trafico de Internet.

Para checkout, `smoke` enfrenta 4 compradores contra 2 unidades y `baseline`
enfrenta 20 compradores contra 10 unidades. Cada comprador ejecuta una sola
iteracion con una sesion distinta. Debe haber exactamente tantas compras
exitosas como unidades iniciales, y el resto debe recibir un rechazo `400`
controlado.

El escenario de cupon usa las mismas cantidades: 4 compradores y 2 usos en
`smoke`, 20 compradores y 10 usos en `baseline`. Cada comprador recibe un
producto diferente con stock propio; exactamente `max_uses` ordenes deben
obtener el descuento.

La prueba falla cuando:

- al menos 1 % de las solicitudes HTTP falla;
- 1 % o mas de los checks funcionales falla;
- p95 del catalogo supera 750 ms o p99 supera 1500 ms;
- p95 de la pagina principal supera 1000 ms;
- p95 de health supera 300 ms.
- checkout vende mas o menos unidades que el inventario inicial;
- un rechazo devuelve un estado inesperado, como `403`, `429` o `5xx`;
- un reintento idempotente crea otra orden o devuelve una orden diferente;
- MySQL no termina con stock cero y registros contables consistentes.
- el contador del cupon supera `max_uses` o no coincide con las ordenes;
- una orden aceptada omite el descuento o un rechazo consume inventario.

Los resultados y el consumo puntual del contenedor se guardan como artefactos
de GitHub Actions durante 30 dias.

Los `400` por agotamiento son parte esperada del escenario de contencion. k6
los clasifica como respuestas controladas, pero un verificador independiente
consulta MySQL al terminar y exige el conteo exacto de exitos, rechazos,
replays, items, movimientos y eventos.

## Ejecucion local

Con la aplicacion disponible en `http://127.0.0.1:8080`:

```powershell
New-Item -ItemType Directory -Force performance-results | Out-Null
docker run --rm `
  --network host `
  --volume "${PWD}\performance:/scripts:ro" `
  --volume "${PWD}\performance-results:/results" `
  --workdir /results `
  --env BASE_URL=http://127.0.0.1:8080 `
  --env LOAD_PROFILE=smoke `
  grafana/k6:2.0.0@sha256:a33a0cfdc4d2483d6b7a3a22e726a499ff2831a671a49239104cd34a9937523c `
  run /scripts/catalog.js
```

En Docker Desktop para Windows, si `--network host` no alcanza el servicio,
usa `BASE_URL=http://host.docker.internal:8080`.

Validacion estatica sin Docker:

```powershell
python .\scripts\check_capacity_config.py
python -m unittest discover -s .\scripts\tests -v
```

## Ajuste antes de produccion

Cuando exista hosting, ejecutar `baseline` contra un staging equivalente y
registrar al menos:

- p50, p95 y p99 por endpoint;
- tasa de errores y timeouts;
- CPU, memoria y reinicios de cada contenedor;
- conexiones, consultas lentas, CPU y almacenamiento de MySQL;
- ancho de banda y latencia desde otra red.

Escalar o investigar cuando p95 incumpla dos ejecuciones consecutivas, CPU
permanezca sobre 70 %, memoria supere 80 %, existan reinicios por OOM o la base
de datos agote conexiones. Primero se identifica el cuello de botella; aumentar
workers sin memoria o conexiones suficientes puede empeorar la estabilidad.

Antes del lanzamiento tambien hacen falta escenarios de cancelacion de
pedidos, carga de imagenes y recuperacion tras saturacion.
