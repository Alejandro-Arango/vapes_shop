from django.db import models

# ======================================================
#  MODELOS BASE DE LA APLICACIÓN 'store'
# ------------------------------------------------------
# Este archivo define las clases (modelos) que representan
# las tablas principales de nuestra base de datos para la
# tienda virtual 'Vapes Shop'.
#
# Cada clase hereda de 'models.Model' y define atributos
# que se convertirán en columnas dentro de la base de datos.
# ======================================================


# ------------------------------------------------------
#  Modelo: Customer (Cliente)
# ------------------------------------------------------
# Representa a una persona que puede realizar compras en la tienda.
# Contiene información básica de identificación y contacto.
# ------------------------------------------------------
class Customer(models.Model):
    first_name = models.CharField(max_length=100)   # Nombre del cliente
    last_name = models.CharField(max_length=100)    # Apellido del cliente
    email = models.EmailField(unique=True)          # Correo electrónico único
    phone = models.CharField(max_length=15, blank=True, null=True)  # Teléfono (opcional)
    date_joined = models.DateTimeField(auto_now_add=True)  # Fecha de registro automático

    def __str__(self):
        # Esta función define cómo se mostrará el objeto cuando se imprime
        return f"{self.first_name} {self.last_name}"


# ------------------------------------------------------
# Modelo: Product (Producto)
# ------------------------------------------------------
# Representa los productos disponibles para la venta.
# Incluye nombre, descripción, precio, cantidad y fecha de registro.
# ------------------------------------------------------
class Product(models.Model):
    name = models.CharField(max_length=200)         # Nombre del producto
    description = models.TextField(blank=True)      # Descripción detallada (opcional)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Precio con 2 decimales
    stock = models.PositiveIntegerField(default=0)  # Cantidad disponible en inventario
    created_at = models.DateTimeField(auto_now_add=True)  # Fecha de creación automática

    def __str__(self):
        return self.name


# ------------------------------------------------------
#  Modelo: Order (Pedido)
# ------------------------------------------------------
# Representa una orden o compra realizada por un cliente.
# Cada pedido pertenece a un cliente y puede tener múltiples productos.
# ------------------------------------------------------
class Order(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)  # Relación con cliente
    date_ordered = models.DateTimeField(auto_now_add=True)            # Fecha del pedido
    completed = models.BooleanField(default=False)                    # Estado del pedido

    def __str__(self):
        return f"Orden #{self.id} - {self.customer}"


# ------------------------------------------------------
#  Modelo: OrderItem (Detalle del pedido)
# ------------------------------------------------------
# Representa los productos individuales dentro de una orden.
# Cada OrderItem está asociado a un producto y a una orden específica.
# ------------------------------------------------------
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)        # Relación con el pedido
    product = models.ForeignKey(Product, on_delete=models.CASCADE)    # Relación con el producto
    quantity = models.PositiveIntegerField(default=1)                 # Cantidad del producto

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    # Propiedad útil para calcular el subtotal del producto dentro de la orden
    @property
    def get_total(self):
        return self.product.price * self.quantity

