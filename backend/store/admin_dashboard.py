"""
Archivo: admin_dashboard.py
Descripcion: Agrega un resumen administrativo con metricas basicas del negocio.
Dependencias: Django admin, agregaciones ORM y modelos de store
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib import admin
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone

from .models import Customer, Order, OrderItem, Product


REVENUE_STATUSES = (
    "pagado",
    "en_preparacion",
    "enviado",
    "entregado",
)
LOW_STOCK_THRESHOLD = 3


def quantize_money(value):
    """
    Nombre: quantize_money
    Descripcion: Normaliza valores monetarios para mostrarlos en el resumen admin.
    """
    return Decimal(value or "0.00").quantize(Decimal("0.01"))


def aggregate_money(queryset, field_name):
    """
    Nombre: aggregate_money
    Descripcion: Suma un campo monetario y devuelve cero cuando no hay resultados.
    """
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field_name),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )["total"]

    return quantize_money(total)


def build_status_rows():
    """
    Nombre: build_status_rows
    Descripcion: Agrupa pedidos por estado para el resumen administrativo.
    """
    labels = dict(Order.STATUS_CHOICES)
    counts = {
        row["status"]: row["total"]
        for row in Order.objects.values("status").annotate(total=Count("id"))
    }

    return [
        {
            "status": status,
            "label": label,
            "count": counts.get(status, 0),
        }
        for status, label in Order.STATUS_CHOICES
    ]


def build_top_products(limit=5):
    """
    Nombre: build_top_products
    Descripcion: Calcula productos mas vendidos por unidades y valor vendido.
    """
    line_revenue = ExpressionWrapper(
        F("unit_price") * F("quantity"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    return list(
        OrderItem.objects
        .filter(order__status__in=REVENUE_STATUSES)
        .values("product_name")
        .annotate(
            units_sold=Coalesce(Sum("quantity"), Value(0)),
            revenue=Coalesce(
                Sum(line_revenue),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
        .order_by("-units_sold", "-revenue", "product_name")[:limit]
    )


def build_business_dashboard_context():
    """
    Nombre: build_business_dashboard_context
    Descripcion: Construye metricas principales para el panel administrativo.
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_30_days = now - timedelta(days=30)
    revenue_orders = Order.objects.filter(status__in=REVENUE_STATUSES)
    revenue_last_30_days = revenue_orders.filter(date_ordered__gte=last_30_days)
    paid_orders_count = revenue_orders.count()
    revenue_total = aggregate_money(revenue_orders, "total_amount")
    average_order_value = Decimal("0.00")

    if paid_orders_count:
        average_order_value = quantize_money(revenue_total / paid_orders_count)

    return {
        "dashboard_url": reverse("admin:store_business_dashboard"),
        "total_orders": Order.objects.count(),
        "orders_today": Order.objects.filter(date_ordered__gte=today_start).count(),
        "orders_last_30_days": Order.objects.filter(date_ordered__gte=last_30_days).count(),
        "revenue_total": revenue_total,
        "revenue_last_30_days": aggregate_money(revenue_last_30_days, "total_amount"),
        "average_order_value": average_order_value,
        "customer_count": Customer.objects.count(),
        "active_product_count": Product.objects.filter(is_active=True).count(),
        "low_stock_products": Product.objects.filter(
            is_active=True,
            stock__lte=LOW_STOCK_THRESHOLD,
        ).order_by("stock", "name")[:8],
        "status_rows": build_status_rows(),
        "top_products": build_top_products(),
        "recent_orders": (
            Order.objects
            .select_related("customer", "customer__user")
            .order_by("-date_ordered", "-id")[:8]
        ),
    }


def business_dashboard_view(request, site=admin.site):
    """
    Nombre: business_dashboard_view
    Descripcion: Renderiza el resumen administrativo protegido por el admin.
    """
    context = {
        **site.each_context(request),
        **build_business_dashboard_context(),
        "title": "Resumen del negocio",
    }

    return TemplateResponse(
        request,
        "admin/store/business_dashboard.html",
        context,
    )


def register_business_dashboard(site=admin.site):
    """
    Nombre: register_business_dashboard
    Descripcion: Registra la URL y el enlace del dashboard dentro del AdminSite.
    """
    if getattr(site, "_store_business_dashboard_registered", False):
        return

    original_get_urls = site.get_urls

    def get_urls():
        custom_urls = [
            path(
                "store/resumen/",
                site.admin_view(lambda request: business_dashboard_view(request, site)),
                name="store_business_dashboard",
            ),
        ]

        return custom_urls + original_get_urls()

    site.get_urls = get_urls
    site.index_template = "admin/store/index.html"
    site._store_business_dashboard_registered = True
