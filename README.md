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
- No-cache para APIs sensibles.
- Rate limits en autenticacion, contacto, carrito y checkout.
- Auditoria interna con redaccion de datos sensibles.
- Validacion de IP en auditoria.
- Ruta de admin configurable.
- Restriccion opcional del admin por IP.
- Cache configurable para evitar `LocMemCache` en produccion.
- Comando `production_check` para bloquear configuraciones inseguras.
- CI con validaciones, pruebas y simulacion de configuracion productiva.

Aspectos que siguen dependiendo del proveedor de despliegue:

- Dominio real y certificado HTTPS.
- Proxy correctamente configurado.
- Base de datos productiva, backups y usuario limitado.
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
DJANGO_DB_ENGINE
DJANGO_DB_NAME
DJANGO_DB_USER
DJANGO_DB_PASSWORD
DJANGO_DB_HOST
DJANGO_DB_PORT
DJANGO_CACHE_BACKEND
DJANGO_CACHE_TABLE
DJANGO_SESSION_COOKIE_SECURE
DJANGO_CSRF_COOKIE_SECURE
DJANGO_SECURE_SSL_REDIRECT
DJANGO_SECURE_HSTS_SECONDS
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS
DJANGO_SECURE_HSTS_PRELOAD
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
DEFAULT_FROM_EMAIL
CONTACT_NOTIFICATION_EMAIL
CONTACT_WHATSAPP_NUMBER
```

## Mejoras Futuras

- Pasarela de pagos real.
- Despliegue en producción.
- PostgreSQL.
- Recuperación de contraseña.
- Sistema de roles.
- Dashboard con métricas.
- Categorías reales para productos.
- Control avanzado de inventario.
- Notificaciones transaccionales por correo.
- Facturación.
- Docker.
- Pruebas frontend.
- Optimización responsive adicional.

## Actualizacion Operativa

El proyecto ya incluye mejoras posteriores a la primera documentacion:

- CI con GitHub Actions.
- Trazabilidad interna mediante `EventLog`.
- Exportacion CSV desde el admin para ordenes, contactos y eventos.
- Estados de pedido ampliados: `pendiente`, `pagado`, `en_preparacion`, `enviado`, `entregado`, `cancelado`, `reembolsado`.
- Configuracion por variables de entorno usando `.env`.
- Archivo `.env.example` como referencia segura.
- Soporte configurable para base de datos `sqlite` o `mysql`.
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

### Pedidos

Desde `Store > Ordenes` el administrador puede:

- Revisar comprador, datos de envio, total, estado, fechas y productos del pedido.
- Cambiar el estado de una orden.
- Usar acciones masivas para marcar ordenes como pagadas, en preparacion, enviadas, entregadas, canceladas o reembolsadas.
- Registrar datos de envio como transportadora, numero de guia y URL de seguimiento.
- Exportar ordenes seleccionadas en CSV.

Cuando una orden pasa a `enviado` o `entregado`, el sistema intenta notificar al cliente por correo si hay configuracion SMTP disponible.

### Reportes del negocio

Desde el inicio del admin se puede entrar a `Ver resumen del negocio`.

El resumen incluye:

- Ventas del periodo seleccionado.
- Cantidad de pedidos por estado.
- Productos mas vendidos.
- Productos con bajo stock.
- Pedidos recientes.

Tambien se pueden descargar reportes CSV de ventas y productos usando filtros de fecha.

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
13. Verificar `python manage.py check --deploy`.
14. Verificar `python manage.py production_check`.

Comandos recomendados:

```powershell
cd C:\dev\vapes_shop\backend
python manage.py check --deploy
python manage.py production_check
python manage.py migrate
python manage.py createcachetable
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
DJANGO_DB_ENGINE
DJANGO_DB_NAME
DJANGO_DB_USER
DJANGO_DB_PASSWORD
DJANGO_DB_HOST
DJANGO_DB_PORT
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
DJANGO_USE_X_FORWARDED_PROTO
DJANGO_TRUST_X_FORWARDED_FOR
AUTH_THROTTLE_RATE
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
DEFAULT_FROM_EMAIL
CONTACT_NOTIFICATION_EMAIL
CONTACT_WHATSAPP_NUMBER
DJANGO_STORE_LOG_LEVEL
DJANGO_REQUEST_LOG_LEVEL
```

## Autor

Proyecto desarrollado por Alejandro Arango como proyecto académico de desarrollo de software.
