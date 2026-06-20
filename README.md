# Vape Shop / vapes_shop

## Descripción

Vape Shop es una tienda e-commerce desarrollada como proyecto académico con Django, Django REST Framework, templates HTML, CSS personalizado y JavaScript vanilla.

El sistema permite explorar productos, gestionar un carrito de compras, registrarse, iniciar sesión, realizar pedidos, consultar historial, cancelar órdenes y administrar productos desde el panel de Django.

## Objetivo

Construir una aplicación web funcional que simule el flujo principal de una tienda en línea: catálogo, carrito, checkout, usuarios, pedidos, administración e inventario básico.

## Alcance Actual

El proyecto incluye:

- Catálogo dinámico de productos.
- Búsqueda por nombre o descripción.
- Filtros por disponibilidad.
- Ordenamiento por precio, stock y nombre.
- Filtros rápidos del catálogo.
- Modal de detalle de producto.
- Carrito lateral.
- Agregar, disminuir, eliminar y vaciar productos.
- Control de stock máximo.
- Subtotal por producto.
- Checkout por pasos.
- Formulario de datos de envío.
- Registro, login, logout y consulta del usuario actual.
- Recuperacion de contrasena por correo con token temporal.
- Cambio de contrasena desde el perfil autenticado.
- Modal de compra exitosa.
- Historial de pedidos.
- Cancelación de pedidos.
- Devolución de stock al cancelar pedidos pagados.
- Timeline visual del estado del pedido.
- Verificación de edad.
- Aviso legal para productos de vapeo.
- Formulario de contacto con registro en base de datos.
- Enlace de WhatsApp con mensaje prellenado.
- Notificación de contacto por correo en modo desarrollo.
- Panel administrativo mejorado.
- Pruebas automatizadas para flujos principales.

## Tecnologías

### Backend

- Python
- Django
- Django REST Framework
- SQLite en desarrollo
- WhiteNoise

### Frontend

- HTML5 con templates de Django
- CSS personalizado
- JavaScript vanilla
- Font Awesome
- AOS Animation Library

### Herramientas

- Git y GitHub
- PowerShell
- Visual Studio Code
- Entorno virtual de Python

## Estructura Principal

```text
vapes_shop/
├── .gitignore
├── README.md
└── backend/
    ├── manage.py
    ├── requirements.txt
    ├── db.sqlite3                # Base local de desarrollo, no debe versionarse
    ├── mi_tienda/
    │   ├── settings.py
    │   ├── urls.py
    │   ├── asgi.py
    │   └── wsgi.py
    └── store/
        ├── admin.py
        ├── apps.py
        ├── models.py
        ├── serializers.py
        ├── tests.py
        ├── urls.py
        ├── views.py
        ├── views_api.py
        ├── views_auth.py
        ├── views_cart.py
        ├── views_contact.py
        ├── views_orders.py
        ├── migrations/
        ├── static/
        │   └── store/
        │       ├── css/style.css
        │       ├── js/app.js
        │       └── img/
        └── templates/
            └── store/
                ├── base.html
                ├── home.html
                └── components/
                    ├── age_verification_modal.html
                    ├── auth_modal.html
                    ├── cart_drawer.html
                    ├── checkout_success_modal.html
                    ├── footer.html
                    ├── header.html
                    ├── orders_modal.html
                    └── product_detail_modal.html
```

## Instalación Local

### 1. Clonar el repositorio

```powershell
git clone URL_DEL_REPOSITORIO
cd vapes_shop
```

### 2. Entrar al backend

```powershell
cd C:\dev\vapes_shop\backend
```

### 3. Activar entorno virtual

Si el entorno está dentro de `backend`:

```powershell
.\.venv\Scripts\Activate.ps1
```

Si usas el entorno de la raíz del proyecto:

```powershell
..\.venv\Scripts\Activate.ps1
```

### 4. Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 5. Aplicar migraciones

```powershell
python manage.py migrate
```

### 6. Ejecutar validaciones

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test store
python manage.py production_check
```

### 7. Ejecutar servidor

```powershell
python manage.py runserver
```

Abrir en el navegador:

```text
http://127.0.0.1:8000/
```

## Panel Administrativo

Crear superusuario:

```powershell
python manage.py createsuperuser
```

Entrar al admin:

```text
http://127.0.0.1:8000/admin/
```

Desde el panel se pueden gestionar:

- Productos.
- Clientes.
- Órdenes.
- Items de orden.
- Contactos recibidos desde el formulario.

## Flujo del Usuario

1. El usuario entra al sitio.
2. Confirma la verificación de edad.
3. Explora productos.
4. Busca, filtra u ordena el catálogo.
5. Abre el detalle de un producto.
6. Agrega productos al carrito.
7. Revisa cantidades, subtotales y stock.
8. Inicia sesión o se registra.
9. Completa datos de envío.
10. Confirma la compra.
11. Recibe un modal de compra exitosa.
12. Consulta su historial de pedidos.
13. Cancela pedidos cuando el estado lo permite.

## Flujo del Administrador

1. Ingresa al panel de Django.
2. Crea o edita productos.
3. Revisa clientes registrados.
4. Revisa pedidos.
5. Cambia estados de órdenes.
6. Usa acciones masivas para marcar órdenes como pagadas, enviadas, entregadas o canceladas.
7. Revisa contactos recibidos.

## Validaciones Realizadas

Validacion recomendada antes de entregar o subir cambios:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test store
python manage.py production_check
```

Resultado:

- `System check identified no issues`.
- Suite de pruebas de `store` ejecutada correctamente.
- Sin migraciones pendientes.
- Configuracion productiva revisada con `production_check`.

## Seguridad y Producción

El proyecto ya incluye una base de endurecimiento para preproduccion:

- Validacion estricta de variables de entorno.
- Cookies seguras configurables.
- HSTS, SSL redirect, Referrer-Policy, COOP y Permissions-Policy.
- Content Security Policy sin scripts inline ni dependencias CDN.
- No-cache para APIs sensibles.
- Rate limits en autenticacion, contacto, carrito y checkout.
- Checkout idempotente para evitar ordenes y descuentos de stock duplicados.
- Proteccion referencial para impedir que eliminar un cliente borre sus pedidos.
- Validacion de imagenes de producto por extension, contenido, peso y dimensiones.
- Restricciones de base de datos para importes no negativos y descuentos validos.
- Consistencia matematica y direccional de movimientos de inventario.
- Unicidad de producto por orden para evitar lineas duplicadas.
- Limites de uso y vigencia de cupones protegidos en base de datos.
- Secuencia valida de fechas de envio y entrega protegida en base de datos.
- Coherencia entre estado operativo y marca de pedido completado.
- Direccion predeterminada unica y estable por cliente.
- Historial de estados validado e inmutable desde el panel administrativo.
- Auditoria interna con redaccion de datos sensibles.
- Validacion de IP en auditoria.
- Liveness del proceso en `/api/live/` y readiness de base de datos/cache en `/api/health/`.
- Identificador `X-Request-ID` para correlacionar solicitudes entre proxy y Django.
- Logs JSON configurables para agregadores externos.
- Ruta de admin configurable.
- Restriccion opcional del admin por IP.
- MFA TOTP obligatorio para el panel administrativo.
- Sesiones administrativas cortas y bloqueo temporal de intentos fallidos.
- Cache configurable para evitar `LocMemCache` en produccion.
- Comando `production_check` para bloquear configuraciones inseguras.
- CI con validaciones, pruebas y simulacion de configuracion productiva.

Aspectos que siguen dependiendo del proveedor de despliegue:

- Dominio real y certificado HTTPS.
- Proxy correctamente configurado.
- Base de datos productiva, usuario limitado y copia cifrada fuera del servidor.
- Servidor de correo transaccional real.
- Monitoreo externo de errores y disponibilidad.
- Politicas legales para venta de productos de vapeo y verificacion de edad fuerte.

## Variables de Entorno Relevantes

```text
DJANGO_DEBUG
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_ADMIN_URL_PATH
DJANGO_ADMIN_ALLOWED_IPS
DJANGO_ADMIN_SESSION_COOKIE_AGE
DJANGO_ADMIN_LOGIN_MAX_ATTEMPTS
DJANGO_ADMIN_LOGIN_LOCKOUT_SECONDS
DJANGO_OTP_TOTP_ISSUER
DJANGO_OTP_TOTP_THROTTLE_FACTOR
DJANGO_OTP_STATIC_THROTTLE_FACTOR
DJANGO_DB_ENGINE
DJANGO_DB_NAME
DJANGO_DB_USER
DJANGO_DB_PASSWORD
DJANGO_DB_HOST
DJANGO_DB_PORT
DJANGO_DB_CONN_MAX_AGE
DJANGO_DB_CONNECT_TIMEOUT
DJANGO_MEDIA_ROOT
DJANGO_CACHE_BACKEND
DJANGO_CACHE_TABLE
DJANGO_SESSION_COOKIE_SECURE
DJANGO_CSRF_COOKIE_SECURE
DJANGO_SECURE_SSL_REDIRECT
DJANGO_SECURE_HSTS_SECONDS
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS
DJANGO_SECURE_HSTS_PRELOAD
DJANGO_CONTENT_SECURITY_POLICY
DJANGO_USE_X_FORWARDED_PROTO
DJANGO_TRUST_X_FORWARDED_FOR
DJANGO_EMAIL_BACKEND
DJANGO_EMAIL_HOST
DJANGO_EMAIL_PORT
DJANGO_EMAIL_HOST_USER
DJANGO_EMAIL_HOST_PASSWORD
DJANGO_EMAIL_USE_TLS
DJANGO_EMAIL_USE_SSL
DJANGO_EMAIL_TIMEOUT
DJANGO_PASSWORD_RESET_TIMEOUT
DEFAULT_FROM_EMAIL
CONTACT_NOTIFICATION_EMAIL
ORDER_NOTIFICATION_EMAIL
INVENTORY_NOTIFICATION_EMAIL
CONTACT_WHATSAPP_NUMBER
DJANGO_LOG_FORMAT
DJANGO_STORE_LOG_LEVEL
DJANGO_REQUEST_LOG_LEVEL
```

## Mejoras Futuras

- Pasarela de pagos real.
- Despliegue en producción.
- PostgreSQL.
- Dashboard con métricas.
- Categorías reales para productos.
- Inventario por lotes o proveedores.
- Notificaciones transaccionales por correo.
- Facturación.
- Orquestacion administrada y almacenamiento de objetos para media.
- Pruebas frontend.
- Optimización responsive adicional.

## Actualizacion Operativa

El proyecto ya incluye mejoras posteriores a la primera documentacion:

- CI con GitHub Actions.
- Trazabilidad interna mediante `EventLog`.
- Exportacion CSV desde el admin para ordenes, contactos, eventos y productos.
- Estados de pedido ampliados: `pendiente`, `pagado`, `en_preparacion`, `enviado`, `entregado`, `cancelado`, `reembolsado`.
- Configuracion por variables de entorno usando `.env`.
- Archivo `.env.example` como referencia segura.
- Soporte configurable para base de datos `sqlite` o `mysql`.
- Recuperacion de contrasena con enlace temporal y expiracion configurable.
- Cambio de contrasena autenticado con validacion de contrasena actual.
- Health check operativo para base de datos y cache.
- Alerta operativa de inventario bajo con comando `notify_low_stock`.
- Historial de movimientos de inventario desde checkout, cancelaciones y acciones admin.
- Proteccion de checkout duplicado mediante claves de idempotencia UUID.
- Conservacion de pedidos historicos aunque se elimine la cuenta de acceso.
- Imagenes de producto limitadas a JPG, PNG, WEBP o AVIF, 5 MB y 5000px por lado.
- Integridad financiera de subtotal, descuento y total protegida en base de datos.
- Movimientos de stock protegidos contra tipos, signos o balances inconsistentes.
- Cada producto solo puede aparecer una vez dentro de la misma orden.
- Cupones protegidos contra usos superiores al limite y fechas invertidas.
- Una entrega requiere fecha de envio y no puede registrarse antes de ella.
- El admin sincroniza automaticamente `completed` al cambiar el estado del pedido.
- Guardados y eliminaciones mantienen una sola direccion predeterminada por cliente.
- El historial rechaza estados invalidos o transiciones sin cambio real.
- Roles administrativos base con comando `setup_store_roles`.
- Validaciones actuales: `python manage.py check`, `python manage.py makemigrations --check --dry-run` y `python manage.py test store`.
- Validacion de preproduccion: `python manage.py production_check`.
- Script local de validacion: `scripts\validate-backend.ps1`.

## Guia Operativa de Administracion

Esta guia resume las tareas diarias que se pueden realizar desde el panel de administracion.

### Acceso al panel

En desarrollo el panel usa la ruta:

```text
http://127.0.0.1:8000/admin/
```

En produccion la ruta debe definirse con `DJANGO_ADMIN_URL_PATH` y el acceso puede limitarse con `DJANGO_ADMIN_ALLOWED_IPS`.

### Roles administrativos

El proyecto incluye grupos base para separar permisos dentro del panel:

- `Operador pedidos`: gestion de ordenes, clientes y seguimiento.
- `Gestor inventario`: gestion de productos, categorias y codigos de descuento.
- `Atencion al cliente`: gestion de contactos, clientes y resenas.
- `Auditor tienda`: permisos de solo lectura para revision operativa.

Para revisar los roles sin modificar la base de datos:

```powershell
cd C:\dev\vapes_shop\backend
.\.venv\Scripts\Activate.ps1
python manage.py setup_store_roles
```

Para crear o actualizar los grupos:

```powershell
python manage.py setup_store_roles --apply
```

El comando es idempotente: puede ejecutarse varias veces sin duplicar permisos.

### MFA administrativo

El panel exige contrasena y un codigo TOTP. Despues de crear el superusuario,
genera un dispositivo pendiente:

```powershell
python manage.py setup_admin_mfa NOMBRE_USUARIO
```

Agrega la clave mostrada a una aplicacion autenticadora y confirma con un
codigo vigente:

```powershell
python manage.py setup_admin_mfa NOMBRE_USUARIO --token 123456
```

El comando entrega diez codigos de recuperacion de un solo uso. Deben guardarse
fuera del servidor. Para reemplazar un dispositivo perdido:

```powershell
python manage.py setup_admin_mfa NOMBRE_USUARIO --replace
```

### Pedidos

Desde `Store > Ordenes` el administrador puede:

- Revisar comprador, datos de envio, total, estado, fechas y productos del pedido.
- Cambiar el estado de una orden.
- Usar acciones masivas para marcar ordenes como pagadas, en preparacion, enviadas, entregadas, canceladas o reembolsadas.
- Registrar datos de envio como transportadora, numero de guia y URL de seguimiento.
- Exportar ordenes seleccionadas en CSV.

Cuando una orden pasa a `enviado` o `entregado`, el sistema intenta notificar al cliente por correo si hay configuracion SMTP disponible.

Desde `Store > Productos` el administrador puede exportar productos seleccionados en CSV para revisar inventario, estado, categoria, precio y stock.

### Reportes del negocio

Desde el inicio del admin se puede entrar a `Ver resumen del negocio`.

El resumen incluye:

- Ventas del periodo seleccionado.
- Cantidad de pedidos por estado.
- Productos mas vendidos.
- Productos con bajo stock.
- Pedidos recientes.

Tambien se pueden descargar reportes CSV de ventas y productos usando filtros de fecha.

### Inventario

Desde `Store > Movimientos de stock` el administrador puede consultar:

- Producto afectado.
- Tipo de movimiento: compra, cancelacion o ajuste administrativo.
- Cantidad movida: negativa para salidas y positiva para entradas.
- Stock antes y despues del movimiento.
- Orden o usuario relacionado cuando aplique.

Para revisar productos activos con bajo stock sin enviar correo:

```powershell
cd C:\dev\vapes_shop\backend
.\.venv\Scripts\Activate.ps1
python manage.py notify_low_stock --threshold 3
```

Para enviar la alerta al correo operativo configurado:

```powershell
python manage.py notify_low_stock --threshold 3 --send-email
```

El destinatario principal es `INVENTORY_NOTIFICATION_EMAIL`. Si no existe, usa `ORDER_NOTIFICATION_EMAIL`.

### Auditoria operativa

Desde el inicio del admin se puede entrar a `Ver auditoria operativa`.

La auditoria permite:

- Buscar eventos por texto.
- Filtrar por tipo de evento, severidad y fechas.
- Revisar usuario, IP, endpoint, metodo HTTP y metadata segura.
- Descargar eventos filtrados en CSV.

Los CSV de auditoria aplican proteccion contra formulas para evitar que valores peligrosos se ejecuten al abrirlos en hojas de calculo.

### Mantenimiento de eventos

Para revisar eventos antiguos sin eliminarlos:

```powershell
cd C:\dev\vapes_shop\backend
.\.venv\Scripts\Activate.ps1
python manage.py purge_event_logs --days 180
```

Para eliminar eventos antiguos de forma confirmada:

```powershell
python manage.py purge_event_logs --days 180 --confirm
```

Tambien se puede filtrar por severidad o tipo:

```powershell
python manage.py purge_event_logs --days 90 --severity info --event-type checkout_success --confirm
```

Sin `--confirm`, el comando solo muestra un resumen y no borra registros.

## Preparacion Produccion

1. Copiar `.env.example` como `.env`.
2. Cambiar `DJANGO_SECRET_KEY`.
3. Definir `DJANGO_ALLOWED_HOSTS`.
4. Definir `DJANGO_CSRF_TRUSTED_ORIGINS`.
5. Configurar base de datos.
6. Configurar cache compartido o cache de base de datos.
7. Cambiar la ruta del admin con `DJANGO_ADMIN_URL_PATH`.
8. Restringir el admin con `DJANGO_ADMIN_ALLOWED_IPS`.
9. Si usas cache de base de datos, ejecutar `python manage.py createcachetable`.
10. Ejecutar migraciones.
11. Ejecutar `collectstatic`.
12. Crear superusuario.
13. Configurar MFA con `python manage.py setup_admin_mfa NOMBRE_USUARIO`.
14. Crear roles administrativos con `python manage.py setup_store_roles --apply`.
15. Verificar `python manage.py check --deploy`.
16. Verificar `python manage.py production_check`.
17. Programar backups y copiar los respaldos cifrados fuera del servidor.
18. Ejecutar periodicamente un simulacro de restauracion.

Comandos recomendados:

```powershell
cd C:\dev\vapes_shop\backend
python manage.py check --deploy
python manage.py production_check
python manage.py migrate
python manage.py createcachetable
python manage.py setup_admin_mfa NOMBRE_USUARIO
python manage.py setup_store_roles --apply
python manage.py collectstatic --noinput
```

Validacion automatizada local:

```powershell
cd C:\dev\vapes_shop
.\scripts\validate-backend.ps1
```

Validacion local con checks de produccion, despues de cargar un `.env` productivo:

```powershell
cd C:\dev\vapes_shop
.\scripts\validate-backend.ps1 -Production
```

Variables principales:

```text
DJANGO_DEBUG
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_ADMIN_URL_PATH
DJANGO_ADMIN_ALLOWED_IPS
DJANGO_ADMIN_SESSION_COOKIE_AGE
DJANGO_ADMIN_LOGIN_MAX_ATTEMPTS
DJANGO_ADMIN_LOGIN_LOCKOUT_SECONDS
DJANGO_OTP_TOTP_ISSUER
DJANGO_OTP_TOTP_THROTTLE_FACTOR
DJANGO_OTP_STATIC_THROTTLE_FACTOR
DJANGO_DB_ENGINE
DJANGO_DB_NAME
DJANGO_DB_USER
DJANGO_DB_PASSWORD
DJANGO_DB_HOST
DJANGO_DB_PORT
DJANGO_DB_CONN_MAX_AGE
DJANGO_DB_CONNECT_TIMEOUT
DJANGO_MEDIA_ROOT
DJANGO_CACHE_BACKEND
DJANGO_CACHE_TABLE
DJANGO_SESSION_COOKIE_SECURE
DJANGO_SESSION_COOKIE_AGE
DJANGO_CSRF_COOKIE_SECURE
DJANGO_SECURE_SSL_REDIRECT
DJANGO_SECURE_HSTS_SECONDS
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS
DJANGO_SECURE_HSTS_PRELOAD
DJANGO_SECURE_REFERRER_POLICY
DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY
DJANGO_CONTENT_SECURITY_POLICY
DJANGO_USE_X_FORWARDED_PROTO
DJANGO_TRUST_X_FORWARDED_FOR
AUTH_THROTTLE_RATE
AUTH_USER_THROTTLE_RATE
CONTACT_THROTTLE_RATE
CART_THROTTLE_RATE
CHECKOUT_THROTTLE_RATE
DJANGO_EMAIL_BACKEND
DJANGO_EMAIL_HOST
DJANGO_EMAIL_PORT
DJANGO_EMAIL_HOST_USER
DJANGO_EMAIL_HOST_PASSWORD
DJANGO_EMAIL_USE_TLS
DJANGO_EMAIL_USE_SSL
DJANGO_EMAIL_TIMEOUT
DJANGO_PASSWORD_RESET_TIMEOUT
DEFAULT_FROM_EMAIL
CONTACT_NOTIFICATION_EMAIL
ORDER_NOTIFICATION_EMAIL
INVENTORY_NOTIFICATION_EMAIL
CONTACT_WHATSAPP_NUMBER
DJANGO_STORE_LOG_LEVEL
DJANGO_REQUEST_LOG_LEVEL
DJANGO_LOG_FORMAT
GUNICORN_WORKERS
GUNICORN_THREADS
GUNICORN_TIMEOUT
```

## Infraestructura con contenedores

El repositorio incluye una base reproducible que no depende de un proveedor:

- Imagen Django no privilegiada basada en Python 3.13.
- Gunicorn como servidor WSGI.
- MySQL 8.4 LTS con volumen persistente y health check.
- Nginx como proxy y servidor de archivos media.
- Migraciones, tabla de cache y roles ejecutados en una tarea de release.
- Volumen persistente separado para imagenes subidas.
- Backups versionados de MySQL y media con checksums.
- Restauracion protegida por confirmacion exacta y respaldo de seguridad previo.
- Liveness independiente para Django y Nginx.
- Readiness de base de datos y cache en `/healthz`.
- Logs JSON correlacionados mediante `X-Request-ID`.
- Sistema de archivos de la aplicacion en modo solo lectura.
- Limites configurables de CPU, memoria y procesos por servicio.
- Pruebas de carga de catalogo con umbrales bloqueantes.
- Validacion automatica de Docker, Compose y recuperacion en GitHub Actions.

Docker debe instalarse antes de ejecutar esta infraestructura localmente.

Preparacion:

```powershell
Copy-Item compose.env.example compose.env
```

Antes de iniciar, reemplaza en `compose.env` la clave de Django y las
contrasenas de MySQL.

Construccion e inicio:

```powershell
docker compose --env-file compose.env up --build -d
```

Estado de los servicios:

```powershell
docker compose --env-file compose.env ps
docker compose --env-file compose.env logs --follow web proxy
```

La aplicacion queda disponible en:

```text
http://127.0.0.1:8080/
```

Creacion del administrador y su MFA:

```powershell
docker compose --env-file compose.env exec web python manage.py createsuperuser
docker compose --env-file compose.env exec web python manage.py setup_admin_mfa NOMBRE_USUARIO
docker compose --env-file compose.env exec web python manage.py setup_admin_mfa NOMBRE_USUARIO --token 123456
```

Para detener los servicios sin borrar datos:

```powershell
docker compose --env-file compose.env down
```

Los volumenes `mysql_data` y `media_data` conservan base de datos e imagenes.
No uses `down --volumes` salvo que quieras eliminarlos deliberadamente.

### Capacidad y pruebas de carga

Compose incluye una linea base de recursos para un host de al menos 2 vCPU y
4 GB de RAM. El workflow `Rendimiento y capacidad` ejecuta un perfil `smoke`
en cada cambio y un perfil `baseline` semanal o manual. Prueba el catalogo
publico y un checkout concurrente sobre MySQL, incluyendo stock limitado,
rechazos controlados, idempotencia, limites globales de cupones y cancelacion
con restauracion unica de inventario.

Validacion estatica local:

```powershell
python .\scripts\check_capacity_config.py
```

Los limites, umbrales, ejecucion local de k6 y criterios de ajuste estan en
[docs/CAPACITY_PLANNING.md](docs/CAPACITY_PLANNING.md).

### Observabilidad

El proxy y Django usan el mismo identificador por solicitud. El valor aparece
en la cabecera `X-Request-ID` y en los logs JSON, lo que permite rastrear un
error sin registrar cuerpos, contrasenas ni parametros de consulta.

Los endpoints operativos tienen responsabilidades distintas:

- `/livez`: confirma que Nginx puede responder.
- `/api/live/`: confirma que el proceso Django puede responder.
- `/healthz`: readiness externa; verifica Django, MySQL y cache.
- `/api/health/`: readiness directa de Django.

Comprobacion manual:

```powershell
curl.exe -i http://127.0.0.1:8080/livez
curl.exe -i http://127.0.0.1:8080/healthz
docker compose --env-file compose.env logs --follow web proxy
```

En produccion, `DJANGO_LOG_FORMAT` debe ser `json`. Los niveles de aplicacion
y solicitudes se controlan con `DJANGO_STORE_LOG_LEVEL` y
`DJANGO_REQUEST_LOG_LEVEL`.

El monitoreo externo debe alertar como minimo por readiness `503`, respuestas
`5xx`, reinicios repetidos de contenedores y fallos del job de recuperacion.

El workflow `Monitor de produccion` consulta `/healthz` cada quince minutos,
pero permanece inactivo hasta configurar en GitHub y publicar el workflow en
la rama predeterminada:

- Variable de repositorio `PRODUCTION_HEALTH_URL` con una URL HTTPS, por
  ejemplo `https://tienda.example/healthz`.
- Secret opcional `MONITOR_WEBHOOK_URL` para recibir alertas JSON.
- Secret opcional `MONITOR_WEBHOOK_TOKEN` si el receptor exige Bearer token.

El webhook incluye campos `text` y `content`, además del evento estructurado,
para facilitar su conexión con un receptor HTTP o una automatización externa.
No incluyas tokens ni datos sensibles en `PRODUCTION_HEALTH_URL`.

Este workflow es una red de seguridad inicial. Los horarios de GitHub Actions
pueden retrasarse y dependen de la disponibilidad de GitHub; una operacion real
debe añadir un monitor de uptime independiente desde otra red o proveedor.

El monitor también puede ejecutarse manualmente:

```powershell
$env:PRODUCTION_HEALTH_URL = "https://DOMINIO_REAL/healthz"
python .\scripts\monitor_production.py
Remove-Item Env:PRODUCTION_HEALTH_URL
```

El procedimiento de clasificación, diagnóstico, mitigación y cierre está en
[docs/INCIDENT_RESPONSE.md](docs/INCIDENT_RESPONSE.md).

### Releases y despliegues controlados

Al publicar una release en GitHub, el workflow `Publicar imagenes de release`
construye y publica en GHCR:

- `ghcr.io/ORGANIZACION/REPOSITORIO`
- `ghcr.io/ORGANIZACION/REPOSITORIO-backup`

No publica `latest`. Cada imagen recibe la etiqueta de la release, una etiqueta
del commit y una atestacion de procedencia. Para desplegar se debe copiar del
resumen del workflow la referencia completa por digest, no solo la etiqueta.
La publicación solo continúa después de validar pruebas, migraciones pendientes
y que la etiqueta use el formato `vMAJOR.MINOR.PATCH`.

En el servidor, conserva el repositorio, copia
`compose.production.env.example` como `compose.production.env`, reemplaza todos
los valores de ejemplo y configura acceso de lectura a GHCR. Si el paquete es
privado, inicia sesion con un token que tenga solo `read:packages`.
Protege `compose.production.env` con permisos exclusivos del usuario de
despliegue. El proxy TLS situado delante de Nginx debe reemplazar, no anexar,
`X-Forwarded-For` y `X-Forwarded-Proto`.

Despliegue:

```powershell
python .\scripts\deploy_production.py `
  --deploy `
  --app-image "ghcr.io/ORGANIZACION/REPOSITORIO@sha256:DIGEST_APP" `
  --backup-image "ghcr.io/ORGANIZACION/REPOSITORIO-backup@sha256:DIGEST_OPS"
```

El proceso:

1. valida Compose y descarga las imagenes;
2. ejecuta `check --deploy` y `production_check` dentro de la imagen;
3. inicia MySQL y crea un backup;
4. ejecuta migraciones;
5. actualiza `web` y `proxy`;
6. verifica `/healthz`;
7. si falla, recupera automáticamente la imagen anterior.

Rollback manual:

```powershell
python .\scripts\deploy_production.py --rollback
```

El estado local se guarda en `.deploy/current.json` y
`.deploy/previous.json`. No contiene secretos.
Si queda `.deploy.lock` tras una interrupcion, elimínalo únicamente después de
confirmar que no existe otro despliegue en ejecución.

El rollback revierte contenedores, no migraciones. Toda migracion productiva
debe ser compatible con la version anterior: primero agregar estructuras
nuevas, despues migrar datos y solo en una release posterior retirar lo
antiguo. Una migracion destructiva elimina la garantia de rollback automatico.

### Seguridad de dependencias e imagenes

El workflow `Seguridad de dependencias e imagenes` se ejecuta en pushes, pull
requests, manualmente y cada lunes. Realiza:

- auditoria bloqueante de dependencias Python con `pip-audit`;
- construccion de las imagenes de aplicacion y operaciones;
- SBOM SPDX JSON de cada imagen;
- escaneo de vulnerabilidades de paquetes del sistema y Python;
- bloqueo ante vulnerabilidades criticas con correccion disponible;
- conservacion de SBOM y reportes durante 30 dias.

Las releases adjuntan los dos SBOM como artefactos y assets de la release,
ademas de las atestaciones de procedencia de GHCR.

Dependabot revisa semanalmente dependencias Python, imagenes Docker y acciones
de GitHub. Las actualizaciones menores y parches se agrupan por ecosistema.
No existe merge automatico: cada PR debe superar CI y revisarse antes de
integrarse.

En GitHub se deben marcar como checks requeridos al menos `Django CI` y
`Seguridad de dependencias e imagenes` antes de permitir merge a la rama
principal. Las releases deben crearse únicamente desde commits que hayan
superado ambos workflows.

Auditoria Python manual:

```powershell
cd C:\dev\vapes_shop
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-security.txt
.\backend\.venv\Scripts\python.exe -m pip_audit `
  --requirement backend\requirements-production.txt `
  --no-deps `
  --strict `
  --progress-spinner off
```

Un hallazgo solo puede ignorarse con un identificador concreto, una
justificacion documentada, alcance revisado y fecha de expiracion. No se deben
desactivar globalmente las auditorias para desbloquear una release.

### Gobierno de seguridad y secretos

El repositorio incluye:

- `SECURITY.md` para divulgacion privada y responsable;
- `CODEOWNERS` para cambios sensibles;
- plantilla de pull request con riesgo, rollback y controles de seguridad;
- deteccion semanal y por commit con Gitleaks;
- verificacion local de archivos `.env`, claves privadas y tokens conocidos;
- inventario y procedimiento de rotacion en
  [docs/SECRETS_MANAGEMENT.md](docs/SECRETS_MANAGEMENT.md).

Validacion local:

```powershell
python .\scripts\check_secret_files.py
python -m unittest discover -s scripts\tests -v
```

Al publicar la rama principal deben activarse en GitHub la proteccion de rama,
revision de `CODEOWNERS`, private vulnerability reporting, secret scanning y
push protection. Un secreto detectado debe revocarse antes de intentar limpiar
el historial.

### Analisis de codigo y seguridad dinamica

`CodeQL` analiza Python y JavaScript en cada push, pull request y semanalmente
con las consultas `security-extended`. Los resultados se publican en la vista
de seguridad de GitHub y deben configurarse como check requerido.

`DAST pasivo` construye una imagen efimera, aplica migraciones sobre SQLite,
crea un producto de prueba y ejecuta OWASP ZAP Baseline. El escaneo usa spider
tradicional y Ajax, pero solo análisis pasivo: no ejecuta ataques activos ni
usa datos productivos.

La politica `.zap/rules.tsv` bloquea problemas de cookies, CSP, framing,
MIME sniffing, Permissions-Policy y divulgacion de errores. HSTS se ignora solo
en esa instancia HTTP efimera porque TLS termina fuera de Django; debe
verificarse contra el dominio real antes de producción.

Validacion local de la politica:

```powershell
python .\scripts\check_zap_rules.py
python -m unittest discover -s scripts\tests -v
```

Los reportes ZAP y logs de la aplicación se conservan como artefactos del
workflow. Una alerta solo debe ignorarse con regla concreta, justificacion y
fecha de revisión.

### Backups y recuperacion

Los respaldos se guardan por defecto en `.\backups`, fuera de los volumenes
de MySQL y media. Cada directorio contiene:

- `database.sql.gz`: volcado logico de MySQL.
- `media.tar.gz`: archivos subidos por los usuarios.
- `metadata.txt`: identificador y fecha UTC.
- `manifest.sha256`: checksums verificados antes de restaurar.

Para crear un respaldo:

```powershell
docker compose --env-file compose.env run --rm backup
Get-Content .\backups\latest.txt
```

`BACKUP_RETENTION_DAYS` controla la retencion local. Su valor predeterminado
es `14`; usa `0` para no eliminar respaldos automaticamente.

El respaldo puede ejecutarse con la tienda activa porque MySQL usa una
transaccion consistente. Si necesitas consistencia estricta entre una fila y
su archivo media, detén temporalmente `web` mientras se genera el respaldo.

La restauracion es destructiva y debe realizarse con la aplicacion detenida.
Requiere confirmar exactamente el identificador UTC del respaldo:

```powershell
docker compose --env-file compose.env stop proxy web

$env:RESTORE_BACKUP_ID = "20260618T230000Z"
$env:RESTORE_CONFIRM = "RESTORE-$env:RESTORE_BACKUP_ID"

docker compose --env-file compose.env run --rm restore
docker compose --env-file compose.env run --rm migrate
docker compose --env-file compose.env up -d web proxy

Remove-Item Env:RESTORE_BACKUP_ID,Env:RESTORE_CONFIRM
```

Antes de sobrescribir datos, el proceso crea otro respaldo salvo que
`RESTORE_CREATE_SAFETY_BACKUP=false`. No desactives esa proteccion en una
restauracion real.

El directorio local de backups protege frente a errores logicos y borrados de
volumen, pero no frente a la perdida completa del servidor. En produccion,
`BACKUP_PATH` debe apuntar a un disco independiente y los respaldos deben
copiarse cifrados a almacenamiento externo con acceso restringido.

El job `Probar respaldo y restauracion` del CI crea datos, genera un respaldo,
altera la base y media, restaura y comprueba que ambos vuelven al valor original.

Este Compose usa HTTP para desarrollo de infraestructura. En produccion se
debe terminar TLS en el proxy o balanceador y activar cookies seguras, HSTS,
redireccion HTTPS, dominio real, SMTP y allowlist administrativa.

## Autor

Proyecto desarrollado por Alejandro Arango como proyecto académico de desarrollo de software.
