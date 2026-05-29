"""
Archivo: admin.py
Descripcion: Configura la visualizacion y gestion de los modelos principales en el panel administrativo de Django.
Dependencias: Django admin y modelos Customer, Product, Order y OrderItem
"""

from django.contrib import admin

from .models import Customer, Product, Order, OrderItem


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """
    Nombre: CustomerAdmin
    Descripcion: Configura la visualizacion, busqueda, filtros y ordenamiento de clientes en el panel administrativo.
    """

    list_display = (
        "id",
        "user",
        "first_name",
        "last_name",
        "email",
        "phone",
        "date_joined",
    )

    search_fields = (
        "user__username",
        "user__email",
        "first_name",
        "last_name",
        "email",
    )

    list_filter = ("date_joined",)

    ordering = ("-date_joined",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Nombre: ProductAdmin
    Descripcion: Configura la visualizacion, busqueda, filtros y ordenamiento de productos en el panel administrativo.
    """

    list_display = (
        "id",
        "name",
        "price",
        "stock",
        "created_at",
    )

    search_fields = ("name", "description")

    list_filter = ("created_at",)

    ordering = ("-created_at",)


class OrderItemInline(admin.TabularInline):
    """
    Nombre: OrderItemInline
    Descripcion: Permite visualizar los productos de una orden directamente dentro del detalle de la orden.
    """

    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """
    Nombre: OrderAdmin
    Descripcion: Configura la visualizacion, busqueda, filtros, detalle y totales de ordenes en el panel administrativo.
    """

    list_display = (
    "id",
    "get_user",
    "customer",
    "shipping_city",
    "date_ordered",
    "status",
    "completed",
    "get_total_order",
)

    list_filter = (
        "status",
        "completed",
        "date_ordered",
    )

    search_fields = (
    "customer__user__username",
    "customer__user__email",
    "customer__email",
    "customer__first_name",
    "customer__last_name",
    "shipping_name",
    "shipping_phone",
    "shipping_address",
    "shipping_city",
)

    ordering = ("-date_ordered",)

    inlines = [OrderItemInline]

    fieldsets = (
    (
        "Informacion general",
        {
            "fields": (
                "customer",
                "status",
                "completed",
            )
        },
    ),
    (
        "Datos de envio",
        {
            "fields": (
                "shipping_name",
                "shipping_phone",
                "shipping_address",
                "shipping_city",
                "shipping_notes",
            )
        },
    ),
)

    def get_user(self, obj):
        return obj.customer.user.username if obj.customer and obj.customer.user else "-"

    get_user.short_description = "Usuario"

    def get_total_order(self, obj):
        total = sum(
            item.product.price * item.quantity
            for item in obj.orderitem_set.all()
        )

        return total

    get_total_order.short_description = "Total"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """
    Nombre: OrderItemAdmin
    Descripcion: Configura la visualizacion, busqueda y subtotal de productos asociados a ordenes.
    """

    list_display = (
        "id",
        "order",
        "product",
        "quantity",
        "get_line_total",
    )

    search_fields = (
        "order__id",
        "product__name",
    )

    ordering = ("-id",)

    def get_line_total(self, obj):
        return obj.product.price * obj.quantity

    get_line_total.short_description = "Subtotal"