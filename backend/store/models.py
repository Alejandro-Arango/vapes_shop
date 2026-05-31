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


class ContactLead(models.Model):
    """
    Nombre: ContactLead
    Descripcion: Registra correos enviados desde el formulario de contacto del home.
    """

    email = models.EmailField()
    whatsapp_message = models.TextField(blank=True)
    email_notification_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.email


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
    CANCELLABLE_STATUSES = {"pendiente", "pagado"}

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    date_ordered = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pendiente"
    )

    shipping_name = models.CharField(max_length=150, blank=True, null=True)
    shipping_phone = models.CharField(max_length=30, blank=True, null=True)
    shipping_address = models.CharField(max_length=200, blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Orden #{self.id} - {self.customer}"

    def can_be_cancelled(self):
        """
        Nombre: can_be_cancelled
        Descripcion: Indica si la orden puede cancelarse sin romper el flujo de compra.
        Retorna: True si el estado permite cancelacion, false en caso contrario.
        """
        return self.status in self.CANCELLABLE_STATUSES

    def should_restore_stock_on_cancel(self):
        """
        Nombre: should_restore_stock_on_cancel
        Descripcion: Indica si al cancelar se debe devolver inventario descontado.
        Retorna: True si la orden ya afecto inventario, false en caso contrario.
        """
        return self.completed or self.status == "pagado"

    def restore_items_stock(self):
        """
        Nombre: restore_items_stock
        Descripcion: Devuelve al inventario las unidades asociadas a los items de la orden.
        """
        items = list(self.orderitem_set.all())
        product_ids = [item.product_id for item in items]

        locked_products = Product.objects.select_for_update().filter(
            id__in=product_ids
        )
        product_map = {
            product.id: product
            for product in locked_products
        }

        for item in items:
            product = product_map.get(item.product_id)

            if not product:
                continue

            product.stock += item.quantity
            product.save(update_fields=["stock"])


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
