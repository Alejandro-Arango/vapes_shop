"""
Archivo: admin_dashboard.py
Descripcion: Agrega un resumen administrativo con metricas basicas y reportes CSV del negocio.
Dependencias: Django admin, agregaciones ORM y modelos de store
"""

import csv
import json

from datetime import datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import admin
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import Customer, EventLog, Order, OrderItem, Product


REVENUE_STATUSES = (
    "pagado",
    "en_preparacion",
    "enviado",
    "entregado",
)
LOW_STOCK_THRESHOLD = 3
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


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


def escape_csv_formula(value):
    """
    Nombre: escape_csv_formula
    Descripcion: Evita formulas ejecutables al abrir reportes CSV en hojas de calculo.
    """
    if not isinstance(value, str):
        return value

    if value.lstrip()[:1] in CSV_FORMULA_PREFIXES:
        return f"'{value}"

    return value


def build_csv_response(filename, headers, rows):
    """
    Nombre: build_csv_response
    Descripcion: Construye una respuesta CSV descargable para reportes administrativos.
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


def parse_report_date(value):
    """
    Nombre: parse_report_date
    Descripcion: Interpreta fechas YYYY-MM-DD recibidas por query string.
    """
    if not value:
        return None

    return parse_date(str(value).strip())


def get_report_date_range(request):
    """
    Nombre: get_report_date_range
    Descripcion: Obtiene rango de fechas opcional para reportes administrativos.
    """
    return (
        parse_report_date(request.GET.get("date_from")),
        parse_report_date(request.GET.get("date_to")),
    )


def apply_report_date_range(queryset, date_from, date_to, field_name="date_ordered"):
    """
    Nombre: apply_report_date_range
    Descripcion: Aplica limites inclusivos por fecha a un queryset.
    """
    current_timezone = timezone.get_current_timezone()

    if date_from:
        start = timezone.make_aware(
            datetime.combine(date_from, time.min),
            current_timezone,
        )
        queryset = queryset.filter(**{f"{field_name}__gte": start})

    if date_to:
        end = timezone.make_aware(
            datetime.combine(date_to, time.max),
            current_timezone,
        )
        queryset = queryset.filter(**{f"{field_name}__lte": end})

    return queryset


def build_report_query(date_from, date_to):
    """
    Nombre: build_report_query
    Descripcion: Construye query string para enlaces de descarga del dashboard.
    """
    query = {}

    if date_from:
        query["date_from"] = date_from.isoformat()

    if date_to:
        query["date_to"] = date_to.isoformat()

    return urlencode(query)


def build_audit_report_query(date_from, date_to, event_type="", severity="", query=""):
    """
    Nombre: build_audit_report_query
    Descripcion: Construye query string para reportes filtrados de auditoria.
    """
    params = {}

    if date_from:
        params["date_from"] = date_from.isoformat()

    if date_to:
        params["date_to"] = date_to.isoformat()

    if event_type:
        params["event_type"] = event_type

    if severity:
        params["severity"] = severity

    if query:
        params["q"] = query

    return urlencode(params)


def format_report_datetime(value):
    """
    Nombre: format_report_datetime
    Descripcion: Convierte fechas de reportes a texto estable.
    """
    if not value:
        return ""

    return timezone.localtime(value).isoformat()


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
    return list(get_sold_products()[:limit])


def get_revenue_orders(date_from=None, date_to=None):
    """
    Nombre: get_revenue_orders
    Descripcion: Obtiene pedidos que cuentan como venta dentro de un rango opcional.
    """
    orders = (
        Order.objects
        .filter(status__in=REVENUE_STATUSES)
        .select_related("customer", "customer__user")
        .order_by("-date_ordered", "-id")
    )

    return apply_report_date_range(orders, date_from, date_to)


def get_sold_products(date_from=None, date_to=None):
    """
    Nombre: get_sold_products
    Descripcion: Agrega productos vendidos dentro de un rango opcional.
    """
    line_revenue = ExpressionWrapper(
        F("unit_price") * F("quantity"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    items = OrderItem.objects.filter(order__status__in=REVENUE_STATUSES)
    items = apply_report_date_range(
        items,
        date_from,
        date_to,
        field_name="order__date_ordered",
    )

    return (
        items
        .values("product_name")
        .annotate(
            units_sold=Coalesce(Sum("quantity"), Value(0)),
            revenue=Coalesce(
                Sum(line_revenue),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
        .order_by("-units_sold", "-revenue", "product_name")
    )


def sales_report_csv_view(request):
    """
    Nombre: sales_report_csv_view
    Descripcion: Descarga pedidos vendidos en CSV con rango de fechas opcional.
    """
    date_from, date_to = get_report_date_range(request)
    rows = (
        (
            order.id,
            format_report_datetime(order.date_ordered),
            str(order.customer),
            order.customer.email,
            order.get_status_display(),
            order.shipping_city or "",
            order.coupon_code,
            str(quantize_money(order.subtotal_amount)),
            str(quantize_money(order.discount_amount)),
            str(quantize_money(order.total_amount)),
        )
        for order in get_revenue_orders(date_from, date_to)
    )

    return build_csv_response(
        "reporte-ventas.csv",
        (
            "Pedido",
            "Fecha",
            "Cliente",
            "Correo",
            "Estado",
            "Ciudad",
            "Cupon",
            "Subtotal",
            "Descuento",
            "Total",
        ),
        rows,
    )


def sold_products_report_csv_view(request):
    """
    Nombre: sold_products_report_csv_view
    Descripcion: Descarga productos vendidos en CSV con rango de fechas opcional.
    """
    date_from, date_to = get_report_date_range(request)
    rows = (
        (
            row["product_name"] or "Producto sin nombre",
            row["units_sold"],
            str(quantize_money(row["revenue"])),
        )
        for row in get_sold_products(date_from, date_to)
    )

    return build_csv_response(
        "reporte-productos-vendidos.csv",
        (
            "Producto",
            "Unidades vendidas",
            "Ventas",
        ),
        rows,
    )


def get_event_type_options():
    """
    Nombre: get_event_type_options
    Descripcion: Lista tipos de evento existentes para filtros del reporte.
    """
    return (
        EventLog.objects
        .order_by("event_type")
        .values_list("event_type", flat=True)
        .distinct()
    )


def get_audit_events(date_from=None, date_to=None, event_type="", severity="", query=""):
    """
    Nombre: get_audit_events
    Descripcion: Filtra eventos de auditoria por fecha, tipo, severidad y busqueda.
    """
    events = EventLog.objects.select_related("user").order_by("-created_at", "-id")
    events = apply_report_date_range(events, date_from, date_to, field_name="created_at")

    if event_type:
        events = events.filter(event_type=event_type)

    valid_severities = {
        severity_key
        for severity_key, _ in EventLog.SEVERITY_CHOICES
    }

    if severity in valid_severities:
        events = events.filter(severity=severity)

    if query:
        events = events.filter(
            Q(event_type__icontains=query)
            | Q(message__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(path__icontains=query)
            | Q(ip_address__icontains=query)
        )

    return events


def audit_events_csv_view(request):
    """
    Nombre: audit_events_csv_view
    Descripcion: Descarga eventos de auditoria filtrados en CSV.
    """
    date_from, date_to = get_report_date_range(request)
    event_type = str(request.GET.get("event_type") or "").strip()
    severity = str(request.GET.get("severity") or "").strip()
    query = str(request.GET.get("q") or "").strip()
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
            format_report_datetime(event.created_at),
        )
        for event in get_audit_events(date_from, date_to, event_type, severity, query)
    )

    return build_csv_response(
        "reporte-auditoria.csv",
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
    date_from, date_to = get_report_date_range(request)
    report_query = build_report_query(date_from, date_to)
    sales_report_url = reverse("admin:store_business_sales_report")
    products_report_url = reverse("admin:store_business_products_report")

    if report_query:
        sales_report_url = f"{sales_report_url}?{report_query}"
        products_report_url = f"{products_report_url}?{report_query}"

    context = {
        **site.each_context(request),
        **build_business_dashboard_context(),
        "title": "Resumen del negocio",
        "report_date_from": date_from.isoformat() if date_from else "",
        "report_date_to": date_to.isoformat() if date_to else "",
        "sales_report_url": sales_report_url,
        "products_report_url": products_report_url,
    }

    return TemplateResponse(
        request,
        "admin/store/business_dashboard.html",
        context,
    )


def audit_dashboard_view(request, site=admin.site):
    """
    Nombre: audit_dashboard_view
    Descripcion: Renderiza busqueda y exportacion operativa de eventos.
    """
    date_from, date_to = get_report_date_range(request)
    event_type = str(request.GET.get("event_type") or "").strip()
    severity = str(request.GET.get("severity") or "").strip()
    query = str(request.GET.get("q") or "").strip()
    report_query = build_audit_report_query(
        date_from,
        date_to,
        event_type,
        severity,
        query,
    )
    audit_report_url = reverse("admin:store_audit_events_report")

    if report_query:
        audit_report_url = f"{audit_report_url}?{report_query}"

    events = get_audit_events(date_from, date_to, event_type, severity, query)
    severity_rows = (
        events
        .order_by()
        .values("severity")
        .annotate(total=Count("id"))
        .order_by("severity")
    )
    context = {
        **site.each_context(request),
        "title": "Auditoria operativa",
        "audit_events": events[:50],
        "audit_total": events.count(),
        "audit_event_types": get_event_type_options(),
        "severity_options": EventLog.SEVERITY_CHOICES,
        "severity_rows": severity_rows,
        "report_date_from": date_from.isoformat() if date_from else "",
        "report_date_to": date_to.isoformat() if date_to else "",
        "selected_event_type": event_type,
        "selected_severity": severity,
        "audit_query": query,
        "audit_report_url": audit_report_url,
    }

    return TemplateResponse(
        request,
        "admin/store/audit_dashboard.html",
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
            path(
                "store/resumen/ventas.csv",
                site.admin_view(sales_report_csv_view),
                name="store_business_sales_report",
            ),
            path(
                "store/resumen/productos-vendidos.csv",
                site.admin_view(sold_products_report_csv_view),
                name="store_business_products_report",
            ),
            path(
                "store/auditoria/",
                site.admin_view(lambda request: audit_dashboard_view(request, site)),
                name="store_audit_dashboard",
            ),
            path(
                "store/auditoria/eventos.csv",
                site.admin_view(audit_events_csv_view),
                name="store_audit_events_report",
            ),
        ]

        return custom_urls + original_get_urls()

    site.get_urls = get_urls
    site.index_template = "admin/store/index.html"
    site._store_business_dashboard_registered = True
