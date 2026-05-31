# Entrega Académica - Vape Shop

## 1. Encabezado del Proyecto

**Nombre:** Vape Shop / vapes_shop
**Tipo:** Proyecto académico de e-commerce
**Tecnologías principales:** Django, Django REST Framework, HTML, CSS, JavaScript vanilla y SQLite
**Autor:** Alejandro Arango
**Estado:** Pausado para entrega académica, con intención de escalar a producción más adelante.

## 2. Introducción

Vape Shop es una aplicación web que simula una tienda en línea para productos de vapeo. El proyecto permite recorrer un catálogo, buscar productos, filtrar disponibilidad, gestionar un carrito, iniciar sesión, registrar usuarios, realizar pedidos y consultar el historial de compras.

El objetivo de esta entrega es presentar una versión funcional y ordenada, adecuada para evaluación académica. El proyecto no se considera una versión final de producción.

## 3. Objetivo General

Desarrollar una aplicación e-commerce funcional que integre backend, frontend, base de datos, autenticación, carrito, pedidos, administración e inventario básico.

## 4. Objetivos Específicos

- Implementar un catálogo dinámico de productos.
- Permitir búsquedas, filtros y ordenamiento.
- Gestionar un carrito de compras con control de stock.
- Crear un flujo de checkout por pasos.
- Registrar usuarios e iniciar sesión.
- Guardar pedidos y datos de envío.
- Permitir consulta y cancelación de pedidos.
- Devolver stock cuando una orden pagada se cancela.
- Mejorar la experiencia visual del usuario.
- Registrar contactos desde el formulario del home.
- Preparar el proyecto para una futura evolución a producción.

## 5. Alcance Actual

El proyecto permite:

- Ver productos.
- Buscar productos.
- Filtrar por disponibilidad.
- Ordenar por precio, stock y nombre.
- Ver detalle de producto en modal.
- Agregar productos al carrito.
- Disminuir, eliminar y vaciar productos.
- Validar stock disponible.
- Completar datos de envío.
- Confirmar compra.
- Ver modal de compra exitosa.
- Consultar historial de pedidos.
- Cancelar pedidos permitidos.
- Registrar leads de contacto.
- Abrir WhatsApp con mensaje prellenado.
- Administrar datos desde Django Admin.

## 6. Tecnologías Utilizadas

### Backend

- **Python:** lenguaje principal.
- **Django:** framework web.
- **Django REST Framework:** endpoints JSON para frontend.
- **SQLite:** base de datos local de desarrollo.
- **WhiteNoise:** soporte para archivos estáticos en despliegues simples.

### Frontend

- **HTML con templates Django:** estructura visual.
- **CSS personalizado:** diseño responsive, modo claro/oscuro y componentes.
- **JavaScript vanilla:** interacción del catálogo, carrito, modales, pedidos y formularios.
- **Font Awesome:** iconos.
- **AOS:** animaciones al hacer scroll.

## 7. Arquitectura General

El proyecto sigue una arquitectura Django tradicional:

- `mi_tienda/` contiene configuración global del proyecto.
- `store/` contiene la aplicación principal de tienda.
- `models.py` define las entidades de negocio.
- `views_*.py` separa responsabilidades por área.
- `urls.py` conecta rutas con vistas.
- `templates/` contiene HTML.
- `static/` contiene CSS, JavaScript e imágenes.

El frontend consume endpoints internos mediante `fetch`, usando sesiones y CSRF de Django.

## 8. Explicación de Carpetas y Archivos

### `backend/`

Carpeta principal del backend. Contiene `manage.py`, la base local, dependencias y las apps Django.

### `backend/mi_tienda/`

Configuración global del proyecto.

- `settings.py`: configuración de apps, base de datos, estáticos, seguridad básica, email y variables de entorno.
- `urls.py`: rutas principales del proyecto y conexión con `store.urls`.
- `asgi.py` y `wsgi.py`: puntos de entrada para servidores.

### `backend/store/`

Aplicación principal de tienda.

- `models.py`: modelos `Customer`, `Product`, `ContactLead`, `Order` y `OrderItem`.
- `serializers.py`: convierte modelos y datos de entrada en JSON validado.
- `admin.py`: personaliza el panel administrativo.
- `urls.py`: rutas de productos, carrito, contacto, autenticación y pedidos.
- `views.py`: renderiza el home.
- `views_api.py`: lista productos.
- `views_auth.py`: registro, login, logout y usuario actual.
- `views_cart.py`: operaciones del carrito.
- `views_contact.py`: formulario de contacto.
- `views_orders.py`: checkout, pedidos y cancelación.
- `tests.py`: pruebas automatizadas.

### `backend/store/templates/store/`

Plantillas HTML.

- `base.html`: plantilla base, carga CSS, JS y componentes globales.
- `home.html`: página principal con información, carrusel, catálogo y contacto.
- `components/`: componentes reutilizables como header, footer, carrito, modales y verificación de edad.

### `backend/store/static/store/`

Archivos estáticos propios de la app.

- `css/style.css`: estilos visuales generales.
- `js/app.js`: lógica frontend.
- `img/`: imágenes usadas por el home y catálogo visual.

## 9. Modelos Principales

### `Product`

Representa productos del catálogo. Guarda nombre, descripción, precio, imagen, stock y fecha de creación.

### `Customer`

Representa los datos del cliente y puede estar asociado a un usuario de Django.

### `ContactLead`

Guarda correos recibidos desde el formulario de contacto, mensaje de WhatsApp generado y si se notificó por correo.

### `Order`

Representa una orden. Guarda cliente, estado, datos de envío, si fue completada y métodos para saber si puede cancelarse o si debe restaurar stock.

### `OrderItem`

Representa un producto dentro de una orden, con cantidad y subtotal.

## 10. Funciones Backend Principales

### `views_api.py`

- `api_products`: devuelve la lista de productos en JSON.

### `views_auth.py`

- `register`: crea usuario, crea cliente asociado e inicia sesión.
- `login_view`: permite login por usuario o correo.
- `logout_view`: cierra sesión.
- `me`: devuelve el usuario autenticado.
- `ensure_customer_for_user`: garantiza que cada usuario tenga un cliente asociado.

### `views_cart.py`

- `api_cart`: devuelve productos del carrito guardado en sesión.
- `api_cart_add`: agrega producto y valida stock.
- `api_cart_decrease`: disminuye cantidad.
- `api_cart_remove`: elimina producto.
- `api_cart_clear`: vacía el carrito.
- `parse_positive_quantity`: valida cantidades positivas.

### `views_orders.py`

- `serialize_order`: convierte una orden en JSON.
- `checkout`: crea orden, guarda envío, descuenta stock y limpia carrito.
- `my_orders`: lista pedidos del usuario autenticado.
- `order_detail`: muestra detalle de una orden del usuario.
- `cancel_order`: cancela órdenes permitidas y restaura stock cuando corresponde.

### `views_contact.py`

- `build_whatsapp_contact`: genera URL de WhatsApp con mensaje prellenado.
- `notify_contact_lead`: intenta enviar correo al administrador.
- `contact`: guarda el contacto y devuelve respuesta al frontend.

## 11. Funciones Frontend Principales

### Utilidades

- `escapeHtml`: evita insertar HTML inseguro.
- `getCookie`: obtiene cookies del navegador.
- `csrfHeaders`: arma headers para peticiones POST protegidas por CSRF.
- `showToast`: muestra mensajes temporales.
- `closeModalSafely`: cierra modales controlando foco.

### Autenticación

- `refreshAuthState`: consulta si hay sesión activa.
- `registerUser`: registra usuarios.
- `loginUser`: inicia sesión.
- `logoutUser`: cierra sesión y limpia estados.

### Productos

- `fetchProducts`: obtiene productos del backend.
- `renderProductsSkeleton`: muestra carga visual.
- `renderProductDetail`: arma el detalle del producto.
- `openProductDetail`: abre modal de producto.
- `renderProducts`: pinta el catálogo.
- `getFilteredCatalogProducts`: aplica filtros y búsqueda.
- `applyCatalogFilters`: actualiza catálogo según filtros.

### Carrito

- `getServerCart`: obtiene carrito de sesión.
- `getLocalCart`: obtiene respaldo local.
- `saveLocalCart`: guarda respaldo local.
- `addToCart`: agrega producto.
- `decreaseCartItem`: disminuye cantidad.
- `removeFromCart`: elimina producto.
- `clearCart`: vacía carrito.
- `updateCartUI`: actualiza vista del carrito.

### Checkout

- `getShippingFormData`: valida datos de envío.
- `clearShippingForm`: limpia formulario.
- `resetCheckoutSummary`: reinicia resumen.
- Lógica de pasos: controla resumen, envío y confirmación.
- Lógica final: envía pedido al backend y muestra confirmación.

### Pedidos

- `fetchMyOrders`: consulta pedidos.
- `cancelOrder`: solicita cancelar pedido.
- `renderShippingInfo`: muestra envío.
- `renderOrderTimeline`: dibuja timeline.
- `renderMyOrders`: pinta historial.

### Contacto

- `submitContactEmail`: envía correo al endpoint de contacto.
- Feedback visual: muestra éxito o error.
- WhatsApp: abre conversación con mensaje prellenado.

## 12. Seguridad

### Aceptable Para Entrega Académica

- Uso de sesiones de Django.
- CSRF en peticiones POST.
- Validación backend de stock.
- Pedidos filtrados por usuario autenticado.
- Cancelación controlada por estado.
- `SECRET_KEY`, `DEBUG` y `ALLOWED_HOSTS` preparados para variables de entorno.

### Pendiente Para Producción

- Configurar `DJANGO_DEBUG=False`.
- Configurar dominio real en `DJANGO_ALLOWED_HOSTS`.
- Usar `DJANGO_SECRET_KEY` seguro.
- Usar PostgreSQL o MySQL en producción.
- Configurar SMTP real.
- Agregar rate limit o captcha al contacto.
- Agregar pasarela de pago real.
- Configurar HTTPS.
- Revisar política de privacidad y datos personales.
- Reforzar verificación de edad.
- Configurar almacenamiento media.

## 13. Pruebas Realizadas

Comandos ejecutados por el usuario:

```powershell
python manage.py check
python manage.py test store
```

Resultado:

- `System check identified no issues`.
- `10 tests` ejecutados.
- Resultado: `OK`.

## 14. Cómo Probar el Proyecto

### Probar catálogo

1. Abrir `http://127.0.0.1:8000/`.
2. Revisar productos.
3. Buscar por nombre.
4. Filtrar por disponibilidad.
5. Ordenar productos.

### Probar carrito

1. Agregar producto.
2. Abrir carrito.
3. Aumentar/disminuir.
4. Eliminar producto.
5. Vaciar carrito.

### Probar checkout

1. Iniciar sesión.
2. Agregar producto.
3. Ir al carrito.
4. Continuar al paso de envío.
5. Completar datos.
6. Confirmar compra.

### Probar pedidos

1. Hacer una compra.
2. Abrir "Mis pedidos".
3. Revisar historial.
4. Cancelar pedido permitido.
5. Confirmar devolución de stock.

### Probar contacto

1. Ir a la sección Contacto.
2. Ingresar correo.
3. Enviar formulario.
4. Confirmar mensaje visual.
5. Confirmar apertura de WhatsApp.
6. Revisar `ContactLead` en admin.

## 15. Capturas Recomendadas

- Home completo.
- Verificación de edad.
- Catálogo con productos.
- Búsqueda/filtros.
- Modal de producto.
- Carrito con productos.
- Checkout paso de envío.
- Confirmación de compra.
- Historial de pedidos.
- Timeline de pedido.
- Cancelación de pedido.
- Formulario de contacto.
- Panel admin con productos.
- Panel admin con órdenes.
- Panel admin con contactos.

## 16. Fortalezas

- Buen alcance funcional para entrega académica.
- Separación por vistas según responsabilidad.
- Flujo completo de e-commerce básico.
- Validaciones importantes en backend.
- Pruebas automatizadas para riesgos principales.
- Diseño visual más profesional que una plantilla básica.
- Preparación inicial para variables de entorno.

## 17. Debilidades y Riesgos

- Aún no tiene pasarela de pago real.
- El frontend está concentrado en un `app.js` grande.
- El CSS también es extenso.
- No hay categorías reales en base de datos.
- No hay sistema de roles avanzado.
- El formulario público de contacto no tiene protección anti-spam.
- SQLite es adecuado para desarrollo, no para producción.
- Falta documentación técnica más profunda si se escala.

## 18. Mejoras Futuras

- Pasarela de pagos.
- Despliegue en producción.
- PostgreSQL.
- Recuperación de contraseña.
- Roles de administrador/vendedor/cliente.
- Dashboard de métricas.
- Categorías reales.
- Control de inventario avanzado.
- Facturación.
- Docker.
- CI/CD.
- Pruebas frontend.
- Optimización de rendimiento.
- Mejoras legales para productos regulados.

## 19. Conclusión

Vape Shop cumple con los requisitos de un e-commerce académico funcional. Integra frontend, backend, base de datos, sesiones, carrito, pedidos, admin y validaciones. Para producción todavía requiere trabajo en seguridad, pagos, despliegue, base de datos y cumplimiento legal, pero como entrega académica presenta una base sólida, clara y escalable.
