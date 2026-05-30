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
    Descripcion: Personaliza la administracion de clientes registrados y su relacion con usuarios.
    Retorna: Configuracion administrativa para el modelo Customer.
    """

    list_display = (
        "id",
        "user",
        "first_name",
        "last_name",
        "email",
        "phone",
    )

    search_fields = (
        "user__username",
        "user__email",
        "first_name",
        "last_name",
        "email",
        "phone",
    )

    list_filter = (
        "user__is_active",
    )

    ordering = (
        "first_name",
        "last_name",
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Nombre: ProductAdmin
    Descripcion: Personaliza la administracion de productos, busqueda, filtros, stock y acciones masivas.
    """

    list_display = (
        "id",
        "name",
        "price",
        "stock",
        "get_stock_status",
        "created_at",
    )

    search_fields = (
        "name",
        "description",
    )

    list_filter = (
        "created_at",
        "stock",
    )

    ordering = (
        "-created_at",
    )

    actions = (
        "mark_out_of_stock",
        "increase_stock_by_10",
    )

    def get_stock_status(self, obj):
        if obj.stock <= 0:
            return "Sin stock"

        if obj.stock <= 3:
            return "Stock bajo"

        return "Disponible"
    get_stock_status.short_description = "Estado stock"

    @admin.action(description="Marcar productos seleccionados sin stock")
    def mark_out_of_stock(self, request, queryset):
        updated = queryset.update(stock=0)

        self.message_user(
            request,
            f"{updated} producto(s) marcados sin stock."
        )

    @admin.action(description="Aumentar stock en 10 unidades")
    def increase_stock_by_10(self, request, queryset):
        for product in queryset:
            product.stock += 10
            product.save(update_fields=["stock"])

        self.message_user(
            request,
            f"{queryset.count()} producto(s) actualizados con 10 unidades adicionales."
        )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "quantity",
    )
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """
    Nombre: OrderAdmin
    Descripcion: Personaliza la administracion de ordenes, filtros, busqueda, totales y acciones masivas.
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
        "shipping_city",
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

    actions = (
        "mark_as_paid",
        "mark_as_sent",
        "mark_as_delivered",
        "mark_as_cancelled",
    )

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
        total = sum(item.product.price * item.quantity for item in obj.orderitem_set.all())
        return total
    get_total_order.short_description = "Total"

    @admin.action(description="Marcar ordenes seleccionadas como pagadas")
    def mark_as_paid(self, request, queryset):
        updated = queryset.exclude(status="cancelado").update(
            status="pagado",
            completed=True
        )

        self.message_user(
            request,
            f"{updated} orden(es) marcadas como pagadas."
        )

    @admin.action(description="Marcar ordenes seleccionadas como enviadas")
    def mark_as_sent(self, request, queryset):
        updated = queryset.exclude(status="cancelado").update(
            status="enviado",
            completed=True
        )

        self.message_user(
            request,
            f"{updated} orden(es) marcadas como enviadas."
        )

    @admin.action(description="Marcar ordenes seleccionadas como entregadas")
    def mark_as_delivered(self, request, queryset):
        updated = queryset.exclude(status="cancelado").update(
            status="entregado",
            completed=True
        )

        self.message_user(
            request,
            f"{updated} orden(es) marcadas como entregadas."
        )

    @admin.action(description="Marcar ordenes seleccionadas como canceladas")
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(
            status="cancelado",
            completed=False
        )

        self.message_user(
            request,
            f"{updated} orden(es) marcadas como canceladas."
        )

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """
    Nombre: OrderItemAdmin
    Descripcion: Personaliza la administracion de productos vendidos dentro de las ordenes.
    Retorna: Configuracion administrativa para el modelo OrderItem.
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

    list_filter = (
        "product",
        "order__status",
    )

    ordering = (
        "-order__date_ordered",
    )

    def get_line_total(self, obj):
        return obj.product.price * obj.quantity

    get_line_total.short_description = "Subtotal"