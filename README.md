# VapeShop

## Descripción del proyecto

VapeShop es una aplicación web desarrollada como proyecto académico final. El sistema permite visualizar productos, gestionar un carrito de compras, registrar usuarios, iniciar sesión, realizar pedidos, consultar el historial de compras y cancelar órdenes.

El proyecto está construido con Django en el backend y HTML, CSS y JavaScript en el frontend. La comunicación entre frontend y backend se realiza mediante endpoints API creados con Django REST Framework.

## Estado del proyecto

Proyecto en desarrollo académico.

## Tecnologías utilizadas

### Backend
- Python
- Django
- Django REST Framework
- SQLite
- WhiteNoise

### Frontend
- HTML5
- CSS3
- JavaScript
- Font Awesome
- AOS Animation Library

### Herramientas de desarrollo
- Visual Studio Code
- Git y GitHub
- PowerShell
- Entorno virtual de Python

## Funcionalidades principales

- Visualización de productos disponibles.
- Carga dinámica de productos desde el backend.
- Gestión de carrito de compras.
- Aumento, disminución y eliminación de productos del carrito.
- Validación de stock disponible.
- Registro de usuarios.
- Inicio y cierre de sesión.
- Consulta del usuario autenticado.
- Creación de pedidos mediante checkout.
- Consulta del historial de pedidos.
- Cancelación de pedidos.
- Devolución automática de stock al cancelar una orden.
- Panel administrativo para gestionar clientes, productos, órdenes e items de orden.
- Interfaz responsive con modo oscuro y modo claro.
- Mensajes visuales mediante toasts y feedback en modales.

## Estructura del proyecto

```text
vapes_shop/
│
├── .gitignore
├── README.md
│
└── backend/
    ├── manage.py
    ├── requirements.txt
    ├── db.sqlite3
    │
    ├── mi_tienda/
    │   ├── __init__.py
    │   ├── asgi.py
    │   ├── settings.py
    │   ├── urls.py
    │   └── wsgi.py
    │
    └── store/
        ├── __init__.py
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
        ├── views_orders.py
        │
        ├── migrations/
        │   ├── __init__.py
        │   ├── 0001_initial.py
        │   ├── 0002_product_image_alter_product_description_and_more.py
        │   ├── 0003_alter_order_customer.py
        │   ├── 0004_customer_user.py
        │   ├── 0005_alter_customer_user.py
        │   ├── 0006_alter_customer_user.py
        │   ├── 0007_alter_customer_user.py
        │   ├── 0008_alter_customer_user.py
        │   ├── 0009_order_status_alter_order_customer.py
        │   └── 0010_alter_order_status.py
        │
        ├── static/
        │   └── store/
        │       ├── css/
        │       │   └── style.css
        │       ├── js/
        │       │   └── app.js
        │       └── img/
        │           ├── banner.3.avif
        │           ├── placeholder.png
        │           ├── Pri-var.webp
        │           ├── savage.webp
        │           └── STLTH.webp
        │
        └── templates/
            └── store/
                ├── base.html
                ├── home.html
                └── components/
                    ├── auth_modal.html
                    ├── cart_drawer.html
                    ├── footer.html
                    ├── header.html
                    └── orders_modal.html
```

## Instalación y ejecución

### 1. Clonar el repositorio

```powershell
git clone URL_DEL_REPOSITORIO
cd vapes_shop
```

### 2. Entrar a la carpeta del backend

```powershell
cd backend
```

### 3. Crear entorno virtual

```powershell
python -m venv .venv
```

### 4. Activar entorno virtual en PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
```

### 5. Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 6. Aplicar migraciones

```powershell
python manage.py migrate
```

### 7. Ejecutar servidor local

```powershell
python manage.py runserver
```

### 8. Abrir el proyecto en el navegador

```text
http://127.0.0.1:8000/
```

## Comandos útiles

### Activar entorno virtual

```powershell
.\.venv\Scripts\Activate.ps1
```

### Revisar configuración del proyecto

```powershell
python manage.py check
```

### Crear migraciones

```powershell
python manage.py makemigrations
```

### Aplicar migraciones

```powershell
python manage.py migrate
```

### Crear superusuario

```powershell
python manage.py createsuperuser
```

### Ejecutar servidor local

```powershell
python manage.py runserver
```

### Generar archivo de dependencias

```powershell
pip freeze > requirements.txt
```

### Instalar dependencias

```powershell
pip install -r requirements.txt
```

## Validaciones realizadas

Durante el desarrollo se realizaron las siguientes validaciones:

- Ejecución de `python manage.py check` sin errores.
- Verificación de carga correcta de la página principal.
- Validación de carga dinámica de productos desde el backend.
- Prueba de registro de usuario.
- Prueba de inicio y cierre de sesión.
- Prueba de agregar productos al carrito.
- Prueba de aumentar, disminuir y eliminar productos del carrito.
- Validación de stock insuficiente antes del checkout.
- Prueba de creación de pedidos mediante checkout.
- Prueba de visualización del historial de pedidos.
- Prueba de cancelación de pedidos.
- Verificación de devolución de stock al cancelar una orden.
- Verificación de mensajes visuales en toasts y modales.
- Validación del panel administrativo de Django.
- Confirmación de cambios guardados con Git.

## Autor

Proyecto desarrollado por Alejandro Arango como proyecto académico final de la técnica en desarrollo de software.