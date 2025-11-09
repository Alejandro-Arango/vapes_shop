# 🌬️ Vapes Shop - Tienda Online de Vapes

Página web funcional para una tienda online de vapes, desarrollada con HTML, CSS, JavaScript y MySQL.

## 🚀 Características

- **Catálogo de Productos**: Visualización de productos con filtros por categoría y búsqueda
- **Carrito de Compras**: Sistema completo de carrito con persistencia en localStorage
- **Diseño Responsivo**: Compatible con dispositivos móviles, tablets y escritorio
- **Base de Datos MySQL**: Almacenamiento de productos y pedidos
- **API REST en PHP**: Backend para operaciones CRUD
- **Modo Demo**: Funciona sin base de datos usando datos de ejemplo

## 📋 Requisitos

- Servidor web (Apache, Nginx, etc.)
- PHP 7.4 o superior
- MySQL 5.7 o superior
- Navegador web moderno

## 🔧 Instalación

### 1. Clonar o descargar el repositorio

```bash
git clone https://github.com/Alejandro-Arango/vapes_shop.git
cd vapes_shop
```

### 2. Configurar la base de datos

**Opción A: Importar desde el archivo SQL**

```bash
mysql -u root -p < database.sql
```

**Opción B: Crear manualmente**

1. Acceder a MySQL:
```bash
mysql -u root -p
```

2. Ejecutar el script:
```sql
source database.sql;
```

### 3. Configurar la conexión a la base de datos

Editar el archivo `api/config.php` con las credenciales de tu base de datos:

```php
define('DB_HOST', 'localhost');
define('DB_USER', 'tu_usuario');
define('DB_PASS', 'tu_contraseña');
define('DB_NAME', 'vapes_shop');
```

### 4. Configurar el servidor web

**Opción A: Usar el servidor integrado de PHP (desarrollo)**

```bash
php -S localhost:8000
```

Luego abrir en el navegador: `http://localhost:8000`

**Opción B: Configurar Apache/Nginx**

Copiar los archivos al directorio del servidor web (por ejemplo, `/var/www/html/vapes_shop`).

## 📁 Estructura del Proyecto

```
vapes_shop/
├── index.html          # Página principal
├── css/
│   └── styles.css      # Estilos CSS
├── js/
│   └── app.js          # Lógica JavaScript
├── api/
│   ├── config.php      # Configuración de la base de datos
│   ├── products.php    # API de productos
│   └── orders.php      # API de pedidos
├── images/             # Directorio para imágenes
├── database.sql        # Script de creación de base de datos
└── README.md           # Este archivo
```

## 🎯 Uso

### Modo Demostración (sin base de datos)

La aplicación funciona automáticamente en modo demostración si no puede conectarse a la base de datos. Los productos se cargan desde datos estáticos en JavaScript.

### Modo Producción (con base de datos)

Una vez configurada la base de datos correctamente, la aplicación:
- Carga productos desde MySQL
- Guarda pedidos en la base de datos
- Permite gestión completa del inventario

### Funcionalidades Principales

1. **Navegar por productos**: Ver el catálogo completo con imágenes y descripciones
2. **Filtrar y buscar**: Filtrar por categoría o buscar productos específicos
3. **Añadir al carrito**: Seleccionar productos y añadirlos al carrito
4. **Gestionar carrito**: Modificar cantidades o eliminar productos
5. **Realizar pedido**: Finalizar la compra (guarda en BD o modo demo)

## 🗄️ Base de Datos

### Tablas Principales

- **products**: Almacena información de productos (nombre, precio, categoría, stock)
- **orders**: Registra los pedidos realizados
- **order_items**: Detalle de productos en cada pedido

### Categorías de Productos

- Vapes
- Líquidos
- Accesorios

## 🔐 Seguridad

- Validación de entrada en el backend PHP
- Uso de prepared statements para prevenir SQL injection
- Configuración de CORS para desarrollo
- Manejo de errores sin exponer información sensible

## 🛠️ Desarrollo

### Añadir nuevos productos

1. Vía base de datos:
```sql
INSERT INTO products (name, description, price, category, image, stock) 
VALUES ('Nombre', 'Descripción', 19.99, 'vapes', '🔋', 50);
```

2. Vía código (modo demo):
Editar la función `getDemoProducts()` en `js/app.js`

### Personalización

- **Estilos**: Modificar variables CSS en `css/styles.css`
- **Colores**: Cambiar variables en `:root`
- **Productos demo**: Editar `getDemoProducts()` en `js/app.js`

## 📱 Compatibilidad

- ✅ Chrome (últimas versiones)
- ✅ Firefox (últimas versiones)
- ✅ Safari (últimas versiones)
- ✅ Edge (últimas versiones)
- ✅ Dispositivos móviles (iOS y Android)

## 🤝 Contribuir

Las contribuciones son bienvenidas. Por favor:

1. Fork el proyecto
2. Crear una rama para tu característica (`git checkout -b feature/nueva-caracteristica`)
3. Commit tus cambios (`git commit -m 'Añadir nueva característica'`)
4. Push a la rama (`git push origin feature/nueva-caracteristica`)
5. Abrir un Pull Request

## 📄 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

## 👨‍💻 Autor

Alejandro Arango

## 📞 Soporte

Para preguntas o problemas, por favor abrir un issue en GitHub.
