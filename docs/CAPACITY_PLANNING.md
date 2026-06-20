# Capacidad y rendimiento

Esta guia define una linea base reproducible. No certifica capacidad
productiva: los resultados dependen del proveedor, red, almacenamiento,
base de datos, volumen de datos y trafico real.

## Alcance actual

La prueba `performance/catalog.js` cubre solamente lectura anonima:

- pagina principal;
- categorias;
- catalogo paginado con 24 productos;
- liveness y readiness.

No genera pedidos, sesiones, escritura de carrito, correo ni carga
administrativa. Esos flujos necesitan escenarios separados y datos
descartables antes de abrir la tienda.

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

La prueba falla cuando:

- al menos 1 % de las solicitudes HTTP falla;
- 1 % o mas de los checks funcionales falla;
- p95 del catalogo supera 750 ms o p99 supera 1500 ms;
- p95 de la pagina principal supera 1000 ms;
- p95 de health supera 300 ms.

Los resultados y el consumo puntual del contenedor se guardan como artefactos
de GitHub Actions durante 30 dias.

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

Antes del lanzamiento tambien hacen falta escenarios de checkout autenticado,
cancelacion de pedidos, carga de imagenes y recuperacion tras saturacion.
