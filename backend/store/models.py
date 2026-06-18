"""
Archivo: models.py
Descripcion: Define los modelos principales de la aplicacion store para clientes, productos, ordenes, inventario e items de orden.
Dependencias: Django settings y Django models
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.text import slugify

from PIL import Image, UnidentifiedImageError


PRODUCT_IMAGE_MAX_BYTES = 5 * 1024 * 1024
PRODUCT_IMAGE_MAX_DIMENSION = 5000
PRODUCT_IMAGE_ALLOWED_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "avif")
PRODUCT_IMAGE_FORMAT_BY_EXTENSION = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "avif": "AVIF",
}


def validate_product_image(image_file):
    """
    Nombre: validate_product_image
    Descripcion: Valida tamano, contenido y dimensiones de imagenes de producto.
    """
    if image_file.size > PRODUCT_IMAGE_MAX_BYTES:
        raise ValidationError("La imagen no puede superar 5 MB.")

    initial_position = image_file.tell()

    try:
        image_file.seek(0)
        image = Image.open(image_file)
        image_format = image.format
        width, height = image.size
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("El archivo no contiene una imagen valida.") from exc
    finally:
        image_file.seek(initial_position)

    extension = str(image_file.name or "").rsplit(".", 1)[-1].lower()
    expected_format = PRODUCT_IMAGE_FORMAT_BY_EXTENSION.get(extension)

    if not expected_format or image_format != expected_format:
        raise ValidationError("El formato real de la imagen no esta permitido.")

    if width > PRODUCT_IMAGE_MAX_DIMENSION or height > PRODUCT_IMAGE_MAX_DIMENSION:
        raise ValidationError(
            f"La imagen no puede superar {PRODUCT_IMAGE_MAX_DIMENSION}px por lado."
        )


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
    phone = models.CharField(max_length=30, blank=True, null=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.first_name} {self.last_name}".strip()
            or self.email
        )


class ShippingAddress(models.Model):
    """
    Nombre: ShippingAddress
    Descripcion: Guarda direcciones reutilizables para el checkout de un cliente.
    """

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="shipping_addresses",
    )
    label = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_default", "-updated_at", "-id")
        indexes = [
            models.Index(
                fields=["customer", "is_default"],
                name="shipaddr_customer_default_idx",
            ),
            models.Index(
                fields=["customer", "updated_at"],
                name="shipaddr_customer_updated_idx",
            ),
        ]

    def __str__(self):
        return self.label or f"{self.address} - {self.city}"

    @classmethod
    def ensure_customer_default(cls, customer_id):
        """
        Nombre: ensure_customer_default
        Descripcion: Promueve una direccion cuando el cliente no tiene predeterminada.
        """
        if cls.objects.filter(
            customer_id=customer_id,
            is_default=True,
        ).exists():
            return

        fallback = (
            cls.objects
            .filter(customer_id=customer_id)
            .order_by("-updated_at", "-id")
            .first()
        )

        if fallback:
            cls.objects.filter(id=fallback.id).update(
                is_default=True,
                updated_at=timezone.now(),
            )

    def save(self, *args, **kwargs):
        """
        Nombre: save
        Descripcion: Mantiene una sola direccion predeterminada por cliente.
        """
        with transaction.atomic():
            Customer.objects.select_for_update().get(id=self.customer_id)
            result = super().save(*args, **kwargs)

            if self.is_default:
                ShippingAddress.objects.filter(id=self.id).update(
                    is_default=True,
                )
                ShippingAddress.objects.filter(
                    customer_id=self.customer_id,
                    is_default=True,
                ).exclude(id=self.id).update(is_default=False)
            else:
                self.ensure_customer_default(self.customer_id)
                self.is_default = ShippingAddress.objects.filter(
                    id=self.id,
                    is_default=True,
                ).exists()

        return result

    def delete(self, *args, **kwargs):
        """
        Nombre: delete
        Descripcion: Promueve una direccion de respaldo al eliminar la predeterminada.
        """
        customer_id = self.customer_id

        with transaction.atomic():
            Customer.objects.select_for_update().get(id=customer_id)
            result = super().delete(*args, **kwargs)
            self.ensure_customer_default(customer_id)

        return result


class Category(models.Model):
    """
    Nombre: Category
    Descripcion: Agrupa productos del catalogo para facilitar administracion y filtrado.
    """

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=["is_active", "name"], name="category_active_name_idx"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """
        Nombre: save
        Descripcion: Genera un slug estable cuando la categoria no lo tiene.
        """
        if not self.slug:
            base_slug = slugify(self.name) or "categoria"
            slug = base_slug
            counter = 2

            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)


class Product(models.Model):
    """
    Nombre: Product
    Descripcion: Representa un producto del catalogo con precio, imagen, stock y fecha de creacion.
    """

    name = models.CharField(max_length=150)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(
        upload_to="store/img/products/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=PRODUCT_IMAGE_ALLOWED_EXTENSIONS,
            ),
            validate_product_image,
        ],
    )
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"], name="product_created_idx"),
            models.Index(
                fields=["stock", "created_at"],
                name="product_stock_created_idx",
            ),
            models.Index(
                fields=["is_active", "created_at"],
                name="product_active_date_idx",
            ),
            models.Index(
                fields=["is_active", "stock"],
                name="product_active_stock_idx",
            ),
            models.Index(
                fields=["category", "is_active"],
                name="product_category_active_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="product_price_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(stock__gte=0),
                name="product_stock_non_negative",
            ),
        ]

    def __str__(self):
        return self.name


class FavoriteProduct(models.Model):
    """
    Nombre: FavoriteProduct
    Descripcion: Guarda productos favoritos por usuario para consulta rapida en la tienda.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorite_products",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "created_at"], name="favorite_user_date_idx"),
            models.Index(fields=["product", "created_at"], name="favorite_product_date_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="favorite_user_product_unique",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.product}"


class ProductReview(models.Model):
    """
    Nombre: ProductReview
    Descripcion: Guarda calificaciones y comentarios de usuarios sobre productos activos.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["product", "is_approved", "created_at"],
                name="review_product_status_idx",
            ),
            models.Index(fields=["user", "created_at"], name="review_user_date_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="review_user_product_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_range",
            ),
        ]

    def __str__(self):
        return f"{self.product} - {self.rating}/5"


class ContactLead(models.Model):
    """
    Nombre: ContactLead
    Descripcion: Registra contactos enviados desde el formulario del home y permite darles seguimiento.
    """

    STATUS_CHOICES = [
        ("nuevo", "Nuevo"),
        ("en_proceso", "En proceso"),
        ("respondido", "Respondido"),
        ("cerrado", "Cerrado"),
    ]

    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="nuevo",
    )
    whatsapp_message = models.TextField(blank=True)
    email_notification_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["created_at"], name="contact_created_idx"),
            models.Index(
                fields=["status", "created_at"],
                name="contact_status_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "nuevo",
                        "en_proceso",
                        "respondido",
                        "cerrado",
                    ]
                ),
                name="contact_status_valid",
            ),
        ]

    def __str__(self):
        return self.name or self.email


class EventLog(models.Model):
    """
    Nombre: EventLog
    Descripcion: Guarda eventos relevantes de seguridad, contacto y pedidos para trazabilidad interna.
    """

    SEVERITY_CHOICES = [
        ("info", "Informacion"),
        ("warning", "Advertencia"),
        ("error", "Error"),
    ]

    event_type = models.CharField(max_length=80)
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default="info",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_logs",
    )
    message = models.CharField(max_length=255)
    path = models.CharField(max_length=255, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["created_at"], name="event_created_idx"),
            models.Index(
                fields=["event_type", "created_at"],
                name="event_type_date_idx",
            ),
            models.Index(
                fields=["severity", "created_at"],
                name="event_severity_date_idx",
            ),
            models.Index(
                fields=["user", "created_at"],
                name="event_user_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(severity__in=["info", "warning", "error"]),
                name="event_severity_valid",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.severity}"


class DiscountCode(models.Model):
    """
    Nombre: DiscountCode
    Descripcion: Define cupones de descuento aplicables al carrito antes del checkout.
    """

    DISCOUNT_TYPE_CHOICES = [
        ("percent", "Porcentaje"),
        ("fixed", "Valor fijo"),
    ]

    code = models.CharField(max_length=40, unique=True)
    description = models.CharField(max_length=160, blank=True)
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default="percent",
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    max_uses = models.PositiveIntegerField(blank=True, null=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=["code", "is_active"], name="discount_code_active_idx"),
            models.Index(fields=["is_active", "starts_at", "ends_at"], name="discount_active_dates_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(discount_type="fixed", value__gte=0)
                    | models.Q(discount_type="percent", value__gte=0, value__lte=100)
                ),
                name="discount_value_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(min_order_total__gte=0),
                name="discount_min_total_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(max_uses__isnull=True)
                    | models.Q(used_count__lte=models.F("max_uses"))
                ),
                name="discount_usage_within_limit",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(starts_at__isnull=True)
                    | models.Q(ends_at__isnull=True)
                    | models.Q(starts_at__lte=models.F("ends_at"))
                ),
                name="discount_dates_valid",
            ),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = str(self.code or "").strip().upper()

        super().save(*args, **kwargs)


class Order(models.Model):
    """
    Nombre: Order
    Descripcion: Representa una orden realizada por un cliente y controla su estado dentro del flujo de compra.
    """

    STATUS_CHOICES = [
        ("pendiente", "Pendiente"),
        ("pagado", "Pagado"),
        ("en_preparacion", "En preparacion"),
        ("enviado", "Enviado"),
        ("entregado", "Entregado"),
        ("cancelado", "Cancelado"),
        ("reembolsado", "Reembolsado"),
    ]
    CANCELLABLE_STATUSES = {"pendiente", "pagado"}
    FINAL_STATUSES = {"entregado", "cancelado", "reembolsado"}
    COMPLETED_STATUSES = {"pagado", "en_preparacion", "enviado", "entregado"}

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    checkout_token = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
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
    tracking_carrier = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=80, blank=True)
    tracking_url = models.URLField(max_length=300, blank=True)
    shipped_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    age_verified = models.BooleanField(default=False)
    coupon_code = models.CharField(max_length=40, blank=True)
    subtotal_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    class Meta:
        indexes = [
            models.Index(fields=["date_ordered"], name="order_date_idx"),
            models.Index(
                fields=["customer", "checkout_token"],
                name="order_customer_checkout_idx",
            ),
            models.Index(
                fields=["customer", "date_ordered"],
                name="order_customer_date_idx",
            ),
            models.Index(
                fields=["status", "date_ordered"],
                name="order_status_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "pendiente",
                        "pagado",
                        "en_preparacion",
                        "enviado",
                        "entregado",
                        "cancelado",
                        "reembolsado",
                    ]
                ),
                name="order_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal_amount__gte=0),
                name="order_subtotal_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__gte=0),
                name="order_discount_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="order_total_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__lte=models.F("subtotal_amount")),
                name="order_discount_not_above_subtotal",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(delivered_at__isnull=True)
                    | models.Q(
                        shipped_at__isnull=False,
                        delivered_at__gte=models.F("shipped_at"),
                    )
                ),
                name="order_tracking_dates_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[
                            "pagado",
                            "en_preparacion",
                            "enviado",
                            "entregado",
                        ],
                        completed=True,
                    )
                    | models.Q(
                        status__in=[
                            "pendiente",
                            "cancelado",
                            "reembolsado",
                        ],
                        completed=False,
                    )
                ),
                name="order_status_completed_valid",
            ),
        ]

    def __str__(self):
        return f"Orden #{self.id} - {self.customer}"

    def can_be_cancelled(self):
        """
        Nombre: can_be_cancelled
        Descripcion: Indica si la orden puede cancelarse sin romper el flujo de compra.
        Retorna: True si el estado permite cancelacion, false en caso contrario.
        """
        return self.status in self.CANCELLABLE_STATUSES

    def sync_completed_with_status(self):
        """
        Nombre: sync_completed_with_status
        Descripcion: Sincroniza el indicador completed con el estado operativo.
        """
        self.completed = self.status in self.COMPLETED_STATUSES

    def should_restore_stock_on_cancel(self):
        """
        Nombre: should_restore_stock_on_cancel
        Descripcion: Indica si al cancelar se debe devolver inventario descontado.
        Retorna: True si la orden ya afecto inventario, false en caso contrario.
        """
        return self.completed or self.status == "pagado"

    def restore_items_stock(self, user=None):
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

            stock_before = product.stock
            product.stock += item.quantity
            product.save(update_fields=["stock"])
            StockMovement.objects.create(
                product=product,
                order=self,
                movement_type="cancel_restore",
                quantity=item.quantity,
                stock_before=stock_before,
                stock_after=product.stock,
                user=user,
                reason="Restauracion por cancelacion de pedido.",
            )


class OrderStatusHistory(models.Model):
    """
    Nombre: OrderStatusHistory
    Descripcion: Guarda cada cambio de estado de una orden para seguimiento y auditoria.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    previous_status = models.CharField(
        max_length=20,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Order.STATUS_CHOICES,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
    )
    note = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(
                fields=["order", "created_at"],
                name="order_status_order_date_idx",
            ),
            models.Index(
                fields=["status", "created_at"],
                name="order_status_state_date_idx",
            ),
        ]

    def __str__(self):
        return f"Orden #{self.order_id}: {self.previous_status or '-'} -> {self.status}"


class OrderItem(models.Model):
    """
    Nombre: OrderItem
    Descripcion: Representa un producto especifico dentro de una orden con su cantidad correspondiente.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=150, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "product"],
                name="orderitem_order_product_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="orderitem_quantity_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(unit_price__gte=0)
                    | models.Q(unit_price__isnull=True)
                ),
                name="orderitem_unit_price_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.display_product_name}"

    def save(self, *args, **kwargs):
        """
        Nombre: save
        Descripcion: Congela el nombre y precio del producto al crear el item de una orden.
        """
        if not self.product_name and self.product_id:
            self.product_name = self.product.name

        if self.unit_price is None and self.product_id:
            self.unit_price = self.product.price

        super().save(*args, **kwargs)

    @property
    def display_product_name(self):
        """
        Nombre: display_product_name
        Descripcion: Retorna el nombre guardado de compra o el nombre actual como respaldo.
        """
        return self.product_name or self.product.name

    @property
    def effective_unit_price(self):
        """
        Nombre: effective_unit_price
        Descripcion: Retorna el precio guardado de compra o el precio actual como respaldo.
        """
        return self.unit_price if self.unit_price is not None else self.product.price

    @property
    def get_total(self):
        return self.effective_unit_price * self.quantity


class StockMovement(models.Model):
    """
    Nombre: StockMovement
    Descripcion: Registra entradas y salidas de inventario para trazabilidad operativa.
    """

    MOVEMENT_TYPE_CHOICES = [
        ("checkout", "Salida por compra"),
        ("cancel_restore", "Entrada por cancelacion"),
        ("admin_adjustment", "Ajuste administrativo"),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    movement_type = models.CharField(
        max_length=30,
        choices=MOVEMENT_TYPE_CHOICES,
    )
    quantity = models.IntegerField()
    stock_before = models.PositiveIntegerField()
    stock_after = models.PositiveIntegerField()
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    reason = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["product", "created_at"], name="stockmov_product_date_idx"),
            models.Index(fields=["movement_type", "created_at"], name="stockmov_type_date_idx"),
            models.Index(fields=["order", "created_at"], name="stockmov_order_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__lt=0) | models.Q(quantity__gt=0),
                name="stockmovement_quantity_not_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    movement_type__in=[
                        "checkout",
                        "cancel_restore",
                        "admin_adjustment",
                    ]
                ),
                name="stockmovement_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(movement_type="checkout", quantity__lt=0)
                    | models.Q(movement_type="cancel_restore", quantity__gt=0)
                    | models.Q(movement_type="admin_adjustment")
                ),
                name="stockmovement_direction_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    stock_after=(
                        Cast(
                            models.F("stock_before"),
                            output_field=models.BigIntegerField(),
                        )
                        + models.F("quantity")
                    )
                ),
                name="stockmovement_balance_valid",
            ),
        ]

    def __str__(self):
        return f"{self.product} ({self.quantity:+d})"
