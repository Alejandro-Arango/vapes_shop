"""
Archivo: models.py
Descripcion: Define los modelos principales de la aplicacion store para clientes, productos, ordenes e items de orden.
Dependencias: Django settings y Django models
"""

from django.conf import settings
from django.db import models


class Customer(models.Model):
    """
    Nombre: Customer
    Descripcion: Representa los datos del cliente asociados opcionalmente a un usuario autenticado.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.first_name} {self.last_name}".strip()
            or self.email
        )


class Product(models.Model):
    """
    Nombre: Product
    Descripcion: Representa un producto del catalogo con precio, imagen, stock y fecha de creacion.
    """

    name = models.CharField(max_length=150)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(
        upload_to="store/img/products/",
        blank=True,
        null=True
    )
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Order(models.Model):
    """
    Nombre: Order
    Descripcion: Representa una orden realizada por un cliente y controla su estado dentro del flujo de compra.
    """

    STATUS_CHOICES = [
        ("pendiente", "Pendiente"),
        ("pagado", "Pagado"),
        ("cancelado", "Cancelado"),
        ("enviado", "Enviado"),
        ("entregado", "Entregado"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    date_ordered = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pendiente"
    )

    def __str__(self):
        return f"Orden #{self.id} - {self.customer}"


class OrderItem(models.Model):
    """
    Nombre: OrderItem
    Descripcion: Representa un producto especifico dentro de una orden con su cantidad correspondiente.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def get_total(self):
        return self.product.price * self.quantity