"""
Archivo: admin.py
Descripcion: Configura la visualizacion y gestion de los modelos principales en el panel administrativo de Django.
Dependencias: Django admin y modelos principales de store
"""

from django.contrib import admin
from django.db import transaction

from .models import ContactLead, Customer, EventLog, Product, Order, OrderItem


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


@admin.register(ContactLead)
class ContactLeadAdmin(admin.ModelAdmin):
    """
    Nombre: ContactLeadAdmin
    Descripcion: Permite consultar los correos recibidos desde el formulario de contacto.
    """

    list_display = (
        "id",
        "name",
        "email",
        "phone",
        "status",
        "email_notification_sent",
        "created_at",
    )

    search_fields = (
        "name",
        "email",
        "phone",
        "message",
    )

    list_filter = (
        "status",
        "email_notification_sent",
        "created_at",
    )

    readonly_fields = (
        "whatsapp_message",
        "email_notification_sent",
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )

    actions = (
        "mark_as_new",
        "mark_as_in_progress",
        "mark_as_answered",
        "mark_as_closed",
    )

    fieldsets = (
        (
            "Datos del contacto",
            {
                "fields": (
                    "name",
                    "email",
                    "phone",
                    "message",
                    "status",
                )
            },
        ),
        (
            "Seguimiento tecnico",
            {
                "fields": (
                    "whatsapp_message",
                    "email_notification_sent",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.action(description="Marcar contactos como nuevos")
    def mark_as_new(self, request, queryset):
        updated = queryset.update(status="nuevo")
        self.message_user(request, f"{updated} contacto(s) marcados como nuevos.")

    @admin.action(description="Marcar contactos en proceso")
    def mark_as_in_progress(self, request, queryset):
        updated = queryset.update(status="en_proceso")
        self.message_user(request, f"{updated} contacto(s) marcados en proceso.")

    @admin.action(description="Marcar contactos como respondidos")
    def mark_as_answered(self, request, queryset):
        updated = queryset.update(status="respondido")
        self.message_user(request, f"{updated} contacto(s) marcados como respondidos.")

    @admin.action(description="Cerrar contactos seleccionados")
    def mark_as_closed(self, request, queryset):
        updated = queryset.update(status="cerrado")
        self.message_user(request, f"{updated} contacto(s) cerrados.")


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    """
    Nombre: EventLogAdmin
    Descripcion: Permite consultar eventos internos de seguridad, contacto y pedidos.
    """

    list_display = (
        "id",
        "event_type",
        "severity",
        "user",
        "ip_address",
        "created_at",
    )

    search_fields = (
        "event_type",
        "message",
        "user__username",
        "user__email",
        "ip_address",
        "path",
    )

    list_filter = (
        "event_type",
        "severity",
        "created_at",
    )

    readonly_fields = (
        "event_type",
        "severity",
        "user",
        "message",
        "path",
        "ip_address",
        "user_agent",
        "metadata",
        "created_at",
    )

    ordering = (
        "-created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
        "age_verified",
        "get_total_order",
    )

    list_filter = (
        "status",
        "completed",
        "age_verified",
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
                    "age_verified",
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
        updated = 0
        skipped = 0

        with transaction.atomic():
            orders = (
                queryset
                .select_for_update()
                .prefetch_related("orderitem_set__product")
            )

            for order in orders:
                if not order.can_be_cancelled():
                    skipped += 1
                    continue

                if order.should_restore_stock_on_cancel():
                    order.restore_items_stock()

                order.status = "cancelado"
                order.completed = False
                order.save(update_fields=["status", "completed"])
                updated += 1

        self.message_user(
            request,
            f"{updated} orden(es) canceladas. {skipped} omitida(s) por estado no cancelable."
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
