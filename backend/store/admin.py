"""
Archivo: admin.py
Descripcion: Configura la visualizacion y gestion de los modelos principales en el panel administrativo de Django.
Dependencias: Django admin y modelos principales de store
"""

import csv
import json

from django.contrib import admin
from django.db import transaction
from django.http import HttpResponse

from .audit import log_event
from .models import (
    Category,
    ContactLead,
    Customer,
    EventLog,
    FavoriteProduct,
    Product,
    ProductReview,
    Order,
    OrderItem,
)


def format_admin_bool(value):
    """
    Nombre: format_admin_bool
    Descripcion: Convierte booleanos a texto claro para exportaciones CSV.
    """
    return "Si" if value else "No"


def format_admin_datetime(value):
    """
    Nombre: format_admin_datetime
    Descripcion: Convierte fechas del admin a texto estable para CSV.
    """
    return value.isoformat() if value else ""


def escape_csv_formula(value):
    """
    Nombre: escape_csv_formula
    Descripcion: Evita que hojas de calculo ejecuten valores exportados como formulas.
    """
    if not isinstance(value, str):
        return value

    if value.lstrip()[:1] in ("=", "+", "-", "@"):
        return f"'{value}"

    return value


def build_csv_response(filename, headers, rows):
    """
    Nombre: build_csv_response
    Descripcion: Construye una respuesta CSV descargable para acciones del admin.
    """
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(headers)

    for row in rows:
        writer.writerow(
            escape_csv_formula(value)
            for value in row
        )

    return response


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
        "export_contacts_csv",
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

    @admin.action(description="Exportar contactos seleccionados a CSV")
    def export_contacts_csv(self, request, queryset):
        rows = (
            (
                lead.id,
                lead.name,
                lead.email,
                lead.phone,
                lead.get_status_display(),
                format_admin_bool(lead.email_notification_sent),
                format_admin_datetime(lead.created_at),
                lead.message,
            )
            for lead in queryset.order_by("-created_at")
        )

        return build_csv_response(
            "contactos.csv",
            (
                "ID",
                "Nombre",
                "Correo",
                "Telefono",
                "Estado",
                "Notificacion enviada",
                "Fecha",
                "Mensaje",
            ),
            rows,
        )


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

    actions = (
        "export_events_csv",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Exportar eventos seleccionados a CSV")
    def export_events_csv(self, request, queryset):
        rows = (
            (
                event.id,
                event.event_type,
                event.get_severity_display(),
                event.user.username if event.user else "",
                event.ip_address or "",
                event.path,
                event.message,
                json.dumps(event.metadata, ensure_ascii=True),
                format_admin_datetime(event.created_at),
            )
            for event in queryset.select_related("user").order_by("-created_at")
        )

        return build_csv_response(
            "eventos.csv",
            (
                "ID",
                "Tipo",
                "Severidad",
                "Usuario",
                "IP",
                "Ruta",
                "Mensaje",
                "Metadata",
                "Fecha",
            ),
            rows,
        )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """
    Nombre: CategoryAdmin
    Descripcion: Permite gestionar categorias del catalogo desde el panel administrativo.
    """

    list_display = (
        "id",
        "name",
        "slug",
        "is_active",
        "created_at",
    )

    search_fields = (
        "name",
        "slug",
        "description",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    prepopulated_fields = {
        "slug": ("name",),
    }

    ordering = (
        "name",
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
        "category",
        "price",
        "stock",
        "is_active",
        "get_stock_status",
        "created_at",
    )

    search_fields = (
        "name",
        "category__name",
        "description",
    )

    list_filter = (
        "category",
        "is_active",
        "created_at",
        "stock",
    )

    list_select_related = (
        "category",
    )

    ordering = (
        "-created_at",
    )

    actions = (
        "activate_products",
        "deactivate_products",
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

    @admin.action(description="Activar productos seleccionados")
    def activate_products(self, request, queryset):
        updated = queryset.update(is_active=True)

        self.message_user(
            request,
            f"{updated} producto(s) activados."
        )

    @admin.action(description="Desactivar productos seleccionados")
    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)

        self.message_user(
            request,
            f"{updated} producto(s) desactivados."
        )

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


@admin.register(FavoriteProduct)
class FavoriteProductAdmin(admin.ModelAdmin):
    """
    Nombre: FavoriteProductAdmin
    Descripcion: Permite consultar productos favoritos guardados por usuarios autenticados.
    """

    list_display = (
        "id",
        "user",
        "product",
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__email",
        "product__name",
    )

    list_filter = (
        "created_at",
    )

    readonly_fields = (
        "created_at",
    )

    list_select_related = (
        "user",
        "product",
    )

    ordering = (
        "-created_at",
    )


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    """
    Nombre: ProductReviewAdmin
    Descripcion: Permite moderar calificaciones y comentarios asociados a productos.
    """

    list_display = (
        "id",
        "product",
        "user",
        "rating",
        "is_approved",
        "created_at",
    )

    search_fields = (
        "product__name",
        "user__username",
        "user__email",
        "comment",
    )

    list_filter = (
        "rating",
        "is_approved",
        "created_at",
    )

    list_select_related = (
        "product",
        "user",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "quantity",
        "unit_price",
        "get_line_total",
    )
    can_delete = False

    def get_line_total(self, obj):
        return obj.get_total

    get_line_total.short_description = "Subtotal"


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
        "export_orders_csv",
        "mark_as_paid",
        "mark_as_preparing",
        "mark_as_sent",
        "mark_as_delivered",
        "mark_as_cancelled",
        "mark_as_refunded",
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
        total = sum(item.get_total for item in obj.orderitem_set.all())
        return total
    get_total_order.short_description = "Total"

    def apply_status_action(self, request, queryset, new_status, completed, event_type):
        """
        Nombre: apply_status_action
        Descripcion: Cambia estados desde admin y registra un evento por cada orden afectada.
        """
        updated = 0

        with transaction.atomic():
            orders = (
                queryset
                .exclude(status__in=("cancelado", "reembolsado"))
                .select_for_update()
            )

            for order in orders:
                previous_status = order.status
                order.status = new_status
                order.completed = completed
                order.save(update_fields=["status", "completed"])
                updated += 1

                log_event(
                    event_type,
                    "Estado de orden actualizado desde admin.",
                    request=request,
                    metadata={
                        "order_id": order.id,
                        "previous_status": previous_status,
                        "new_status": new_status,
                    },
                )

        return updated

    @admin.action(description="Exportar ordenes seleccionadas a CSV")
    def export_orders_csv(self, request, queryset):
        queryset = (
            queryset
            .select_related("customer", "customer__user")
            .prefetch_related("orderitem_set__product")
            .order_by("-date_ordered")
        )
        rows = (
            (
                order.id,
                order.customer.user.username if order.customer.user else "",
                order.customer.email,
                order.get_status_display(),
                format_admin_bool(order.completed),
                format_admin_bool(order.age_verified),
                order.shipping_name or "",
                order.shipping_phone or "",
                order.shipping_city or "",
                order.shipping_address or "",
                str(self.get_total_order(order)),
                format_admin_datetime(order.date_ordered),
            )
            for order in queryset
        )

        return build_csv_response(
            "ordenes.csv",
            (
                "ID",
                "Usuario",
                "Correo cliente",
                "Estado",
                "Completada",
                "Edad verificada",
                "Nombre envio",
                "Telefono envio",
                "Ciudad",
                "Direccion",
                "Total",
                "Fecha",
            ),
            rows,
        )

    @admin.action(description="Marcar ordenes seleccionadas como pagadas")
    def mark_as_paid(self, request, queryset):
        updated = self.apply_status_action(
            request,
            queryset,
            "pagado",
            True,
            "admin_order_paid",
        )

        self.message_user(
            request,
            f"{updated} orden(es) marcadas como pagadas."
        )

    @admin.action(description="Marcar ordenes seleccionadas en preparacion")
    def mark_as_preparing(self, request, queryset):
        updated = self.apply_status_action(
            request,
            queryset,
            "en_preparacion",
            True,
            "admin_order_preparing",
        )

        self.message_user(
            request,
            f"{updated} orden(es) marcadas en preparacion."
        )

    @admin.action(description="Marcar ordenes seleccionadas como enviadas")
    def mark_as_sent(self, request, queryset):
        updated = self.apply_status_action(
            request,
            queryset,
            "enviado",
            True,
            "admin_order_sent",
        )

        self.message_user(
            request,
            f"{updated} orden(es) marcadas como enviadas."
        )

    @admin.action(description="Marcar ordenes seleccionadas como entregadas")
    def mark_as_delivered(self, request, queryset):
        updated = self.apply_status_action(
            request,
            queryset,
            "entregado",
            True,
            "admin_order_delivered",
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

                restored_stock = order.should_restore_stock_on_cancel()

                if restored_stock:
                    order.restore_items_stock()

                order.status = "cancelado"
                order.completed = False
                order.save(update_fields=["status", "completed"])
                updated += 1

                log_event(
                    "admin_order_cancelled",
                    "Orden cancelada desde admin.",
                    request=request,
                    metadata={
                        "order_id": order.id,
                        "restored_stock": restored_stock,
                    },
                )

        self.message_user(
            request,
            f"{updated} orden(es) canceladas. {skipped} omitida(s) por estado no cancelable."
        )

    @admin.action(description="Marcar ordenes seleccionadas como reembolsadas")
    def mark_as_refunded(self, request, queryset):
        updated = self.apply_status_action(
            request,
            queryset,
            "reembolsado",
            False,
            "admin_order_refunded",
        )

        self.message_user(
            request,
            f"{updated} orden(es) marcadas como reembolsadas."
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
        "unit_price",
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
        return obj.get_total

    get_line_total.short_description = "Subtotal"
