"""
Archivo: views_orders.py
Descripcion: Gestiona checkout, consulta de pedidos, detalle de orden y cancelacion de pedidos.
Dependencias: Django transaction, Django REST Framework, modelos Product, Customer, Order y OrderItem
"""

import re

from django.db import transaction

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .audit import log_event
from .cart_utils import sync_cart_with_products
from .customer_utils import ensure_customer_for_user
from .models import Product, Customer, Order, OrderItem
from .throttles import CheckoutUserRateThrottle


PHONE_PATTERN = re.compile(r"^[0-9\s()+-]+$")
SHIPPING_MAX_LENGTHS = {
    "name": 150,
    "phone": 30,
    "address": 200,
    "city": 100,
    "notes": 500,
}
MAX_AUDIT_PRODUCT_IDS = 20
ORDER_DEFAULT_PAGE = 1
ORDER_DEFAULT_PAGE_SIZE = 4
ORDER_MAX_PAGE_SIZE = 20


def parse_bool(value):
    """
    Nombre: parse_bool
    Descripcion: Interpreta valores comunes enviados por JSON como booleanos.
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "si")

    return value == 1


def build_cart_audit_metadata(cart):
    """
    Nombre: build_cart_audit_metadata
    Descripcion: Resume el carrito para auditoria sin guardar el payload completo.
    """
    if not isinstance(cart, dict):
        return {
            "cart_items": 0,
            "cart_payload_type": type(cart).__name__,
        }

    product_ids = []
    invalid_items = 0

    for product_id in cart.keys():
        try:
            product_ids.append(int(product_id))
        except (TypeError, ValueError):
            invalid_items += 1

    return {
        "cart_items": len(cart),
        "invalid_items": invalid_items,
        "product_ids": sorted(product_ids)[:MAX_AUDIT_PRODUCT_IDS],
        "product_ids_truncated": len(product_ids) > MAX_AUDIT_PRODUCT_IDS,
    }


def validate_shipping_data(name, phone, address, city, notes):
    """
    Nombre: validate_shipping_data
    Descripcion: Valida datos de envio antes de crear una orden.
    Retorna: Mensaje de error o None si los datos son validos.
    """
    if not name or not phone or not address or not city:
        return "Debes completar los datos de envio"

    if len(name) > SHIPPING_MAX_LENGTHS["name"]:
        return "El nombre de envio es demasiado largo"

    if len(phone) > SHIPPING_MAX_LENGTHS["phone"]:
        return "El telefono de envio es demasiado largo"

    if len(address) > SHIPPING_MAX_LENGTHS["address"]:
        return "La direccion de envio es demasiado larga"

    if len(city) > SHIPPING_MAX_LENGTHS["city"]:
        return "La ciudad de envio es demasiado larga"

    if len(notes) > SHIPPING_MAX_LENGTHS["notes"]:
        return "Las notas de envio son demasiado largas"

    phone_digits = re.sub(r"\D", "", phone)

    if (
        not PHONE_PATTERN.fullmatch(phone)
        or len(phone_digits) < 7
        or len(phone_digits) > 15
    ):
        return "El telefono de envio no es valido"

    return None


def serialize_order(order):
    """
    Nombre: serialize_order
    Descripcion: Convierte una orden en un diccionario con productos, total y datos de envio.
    """
    items = []
    total = 0.0

    for item in order.orderitem_set.all():
        unit_price = item.effective_unit_price
        line_total = float(unit_price) * item.quantity
        total += line_total

        items.append({
            "product": {
                "id": item.product.id,
                "name": item.display_product_name,
                "price": float(unit_price),
                "image": item.product.image.url if item.product.image else "",
            },
            "quantity": item.quantity,
            "line_total": line_total,
        })

    return {
        "id": order.id,
        "date_ordered": order.date_ordered,
        "completed": order.completed,
        "status": order.status,
        "status_label": order.get_status_display(),
        "age_verified": order.age_verified,
        "total": total,
        "shipping": {
            "name": order.shipping_name or "",
            "phone": order.shipping_phone or "",
            "address": order.shipping_address or "",
            "city": order.shipping_city or "",
            "notes": order.shipping_notes or "",
        },
        "items": items,
    }


def get_order_pagination_error(request):
    """
    Nombre: get_order_pagination_error
    Descripcion: Valida parametros de paginacion del historial de pedidos.
    """
    page = request.query_params.get("page")
    page_size = request.query_params.get("page_size")

    if page is not None and not page.strip().isdigit():
        return "Pagina invalida."

    if page is not None and int(page) < 1:
        return "Pagina invalida."

    if page_size is not None and not page_size.strip().isdigit():
        return "Tamano de pagina invalido."

    if page_size is not None:
        clean_page_size = int(page_size)

        if clean_page_size < 1 or clean_page_size > ORDER_MAX_PAGE_SIZE:
            return "Tamano de pagina invalido."

    return ""


def get_order_pagination_params(request):
    """
    Nombre: get_order_pagination_params
    Descripcion: Obtiene pagina y tamano de pagina para el historial de pedidos.
    """
    page = int(request.query_params.get("page", ORDER_DEFAULT_PAGE))
    page_size = int(request.query_params.get("page_size", ORDER_DEFAULT_PAGE_SIZE))

    return page, page_size


def paginate_orders(orders, request):
    """
    Nombre: paginate_orders
    Descripcion: Recorta el queryset de pedidos y construye metadatos de paginacion.
    """
    page, page_size = get_order_pagination_params(request)
    total = orders.count()
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    end = start + page_size

    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1 and total_pages > 0,
    }

    return orders[start:end], pagination


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([CheckoutUserRateThrottle])
def checkout(request):
    """
    Nombre: checkout
    Descripcion: Crea una orden usando el carrito almacenado en sesion, guarda datos de envio y descuenta el stock disponible.
    """
    cart = request.session.get("cart", {})

    if not cart:
        log_event(
            "checkout_failed",
            "Checkout rechazado por carrito vacio.",
            request=request,
            severity="warning",
        )

        return Response(
            {"error": "Carrito vacio"},
            status=status.HTTP_400_BAD_REQUEST
        )

    synced_cart, _, cart_changed = sync_cart_with_products(cart)

    if cart_changed:
        request.session["cart"] = synced_cart
        request.session.modified = True

        metadata = {
            "cart_items_after": len(synced_cart),
        }

        if isinstance(cart, dict):
            metadata["cart_items_before"] = len(cart)
        else:
            metadata["cart_payload_type"] = type(cart).__name__

        log_event(
            "checkout_failed",
            "Checkout detenido porque el carrito fue sincronizado.",
            request=request,
            severity="warning",
            metadata=metadata,
        )

        return Response(
            {
                "error": "Tu carrito fue actualizado por cambios de disponibilidad. Revisalo antes de pagar.",
                "cart_updated": True,
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    cart = synced_cart

    shipping_name = str(
        request.data.get("shippingName")
        or request.data.get("shipping_name")
        or ""
    ).strip()

    shipping_phone = str(
        request.data.get("shippingPhone")
        or request.data.get("shipping_phone")
        or ""
    ).strip()

    shipping_address = str(
        request.data.get("shippingAddress")
        or request.data.get("shipping_address")
        or ""
    ).strip()

    shipping_city = str(
        request.data.get("shippingCity")
        or request.data.get("shipping_city")
        or ""
    ).strip()

    shipping_notes = str(
        request.data.get("shippingNotes")
        or request.data.get("shipping_notes")
        or ""
    ).strip()

    shipping_error = validate_shipping_data(
        shipping_name,
        shipping_phone,
        shipping_address,
        shipping_city,
        shipping_notes,
    )

    if shipping_error:
        log_event(
            "checkout_failed",
            "Checkout rechazado por datos de envio invalidos.",
            request=request,
            severity="warning",
            metadata={"cart_items": len(cart)},
        )

        return Response(
            {"error": shipping_error},
            status=status.HTTP_400_BAD_REQUEST
        )

    age_confirmed = parse_bool(
        request.data.get("ageConfirmed")
        or request.data.get("age_confirmed")
    )

    if not age_confirmed:
        log_event(
            "checkout_failed",
            "Checkout rechazado por falta de confirmacion de edad.",
            request=request,
            severity="warning",
            metadata={"cart_items": len(cart)},
        )

        return Response(
            {"error": "Debes confirmar que cumples con la edad legal requerida"},
            status=status.HTTP_400_BAD_REQUEST
        )

    customer = ensure_customer_for_user(request.user)

    try:
        product_ids = [int(pid) for pid in cart.keys()]
    except ValueError:
        log_event(
            "checkout_failed",
            "Checkout rechazado por carrito invalido.",
            request=request,
            severity="warning",
            metadata=build_cart_audit_metadata(cart),
        )

        return Response(
            {"error": "Carrito invalido"},
            status=status.HTTP_400_BAD_REQUEST
        )

    products = Product.objects.filter(id__in=product_ids, is_active=True)

    if not products.exists():
        log_event(
            "checkout_failed",
            "Checkout rechazado porque no hay productos validos.",
            request=request,
            severity="warning",
            metadata={"product_ids": product_ids},
        )

        return Response(
            {"error": "No hay productos validos en el carrito"},
            status=status.HTTP_400_BAD_REQUEST
        )

    product_map = {
        product.id: product
        for product in products
    }

    unavailable_product_ids = set(product_ids) - set(product_map.keys())

    if unavailable_product_ids:
        log_event(
            "checkout_failed",
            "Checkout rechazado por productos no disponibles.",
            request=request,
            severity="warning",
            metadata={"product_ids": sorted(unavailable_product_ids)},
        )

        return Response(
            {"error": "Uno o mas productos del carrito ya no estan disponibles"},
            status=status.HTTP_400_BAD_REQUEST
        )

    order_lines = []

    for pid_str, qty in cart.items():
        try:
            pid = int(pid_str)
            qty = int(qty)
        except (ValueError, TypeError):
            continue

        if qty <= 0:
            continue

        product = product_map.get(pid)

        if not product:
            continue

        if product.stock < qty:
            log_event(
                "checkout_failed",
                "Checkout rechazado por stock insuficiente.",
                request=request,
                severity="warning",
                metadata={
                    "product_id": product.id,
                    "product_name": product.name,
                    "requested_qty": qty,
                    "available_stock": product.stock,
                },
            )

            return Response(
                {"error": f"Stock insuficiente para {product.name}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_lines.append((product, qty))

    if not order_lines:
        log_event(
            "checkout_failed",
            "Checkout rechazado porque no se pudo procesar el carrito.",
            request=request,
            severity="warning",
            metadata=build_cart_audit_metadata(cart),
        )

        return Response(
            {"error": "No se pudo procesar el carrito"},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        locked_products = Product.objects.select_for_update().filter(
            id__in=[product.id for product, _ in order_lines]
        )

        locked_map = {
            product.id: product
            for product in locked_products
        }

        for product, qty in order_lines:
            locked_product = locked_map.get(product.id)

            if not locked_product:
                log_event(
                    "checkout_failed",
                    "Checkout rechazado porque un producto no esta disponible.",
                    request=request,
                    severity="warning",
                    metadata={"product_id": product.id, "product_name": product.name},
                )

                return Response(
                    {"error": f"Producto no disponible: {product.name}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if locked_product.stock < qty:
                log_event(
                    "checkout_failed",
                    "Checkout rechazado por stock insuficiente al confirmar.",
                    request=request,
                    severity="warning",
                    metadata={
                        "product_id": locked_product.id,
                        "product_name": locked_product.name,
                        "requested_qty": qty,
                        "available_stock": locked_product.stock,
                    },
                )

                return Response(
                    {"error": f"Stock insuficiente para {locked_product.name}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        order = Order.objects.create(
            customer=customer,
            completed=True,
            status="pagado",
            shipping_name=shipping_name,
            shipping_phone=shipping_phone,
            shipping_address=shipping_address,
            shipping_city=shipping_city,
            shipping_notes=shipping_notes,
            age_verified=True,
        )

        total = 0.0

        for product, qty in order_lines:
            locked_product = locked_map[product.id]
            unit_price = locked_product.price

            OrderItem.objects.create(
                order=order,
                product=locked_product,
                product_name=locked_product.name,
                quantity=qty,
                unit_price=unit_price,
            )

            total += float(unit_price) * qty

            locked_product.stock -= qty
            locked_product.save(update_fields=["stock"])

        request.session["cart"] = {}
        request.session.modified = True

    log_event(
        "checkout_success",
        "Compra realizada correctamente.",
        request=request,
        metadata={
            "order_id": order.id,
            "total": total,
            "items": len(order_lines),
        },
    )

    return Response(
        {
            "message": "Compra realizada con exito",
            "order_id": order.id,
            "total_pagado": total,
        },
        status=status.HTTP_200_OK
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    """
    Nombre: my_orders
    Descripcion: Devuelve el historial de pedidos del usuario autenticado con productos, total y datos de envio.
    """
    pagination_error = get_order_pagination_error(request)

    if pagination_error:
        return Response(
            {"error": pagination_error},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        customer = request.user.customer
    except Customer.DoesNotExist:
        return Response(
            {
                "orders": [],
                "pagination": {
                    "page": ORDER_DEFAULT_PAGE,
                    "page_size": ORDER_DEFAULT_PAGE_SIZE,
                    "total": 0,
                    "total_pages": 0,
                    "has_next": False,
                    "has_previous": False,
                },
            },
            status=status.HTTP_200_OK
        )

    user_orders = (
        Order.objects
        .filter(customer=customer)
        .prefetch_related("orderitem_set__product")
        .order_by("-date_ordered")
    )
    user_orders, pagination = paginate_orders(user_orders, request)

    orders = [
        serialize_order(order)
        for order in user_orders
    ]

    return Response(
        {
            "orders": orders,
            "pagination": pagination,
        },
        status=status.HTTP_200_OK
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_detail(request, order_id):
    """
    Nombre: order_detail
    Descripcion: Devuelve el detalle de una orden especifica del usuario autenticado.
    """
    try:
        customer = request.user.customer
    except Customer.DoesNotExist:
        return Response(
            {"error": "Cliente no encontrado"},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        order = (
            Order.objects
            .prefetch_related("orderitem_set__product")
            .get(id=order_id, customer=customer)
        )
    except Order.DoesNotExist:
        log_event(
            "order_detail_failed",
            "Consulta de orden rechazada porque no existe para el usuario.",
            request=request,
            severity="warning",
            metadata={"order_id": order_id},
        )

        return Response(
            {"error": "Orden no encontrada"},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response(
        serialize_order(order),
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_id):
    """
    Nombre: cancel_order
    Descripcion: Cancela una orden del usuario autenticado y devuelve el stock de sus productos.
    """
    try:
        customer = request.user.customer
    except Customer.DoesNotExist:
        log_event(
            "order_cancel_failed",
            "Cancelacion rechazada porque el usuario no tiene customer.",
            request=request,
            severity="warning",
            metadata={"order_id": order_id},
        )

        return Response(
            {"error": "No existe un customer asociado a este usuario"},
            status=status.HTTP_400_BAD_REQUEST
        )

    restored_stock = False

    with transaction.atomic():
        try:
            order = (
                Order.objects
                .select_for_update()
                .prefetch_related("orderitem_set__product")
                .get(id=order_id, customer=customer)
            )
        except Order.DoesNotExist:
            log_event(
                "order_cancel_failed",
                "Cancelacion rechazada porque la orden no existe para el usuario.",
                request=request,
                severity="warning",
                metadata={"order_id": order_id},
            )

            return Response(
                {"error": "Orden no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )

        if order.status in {"cancelado", "reembolsado"}:
            log_event(
                "order_cancel_failed",
                "Cancelacion rechazada porque la orden ya esta cerrada.",
                request=request,
                severity="warning",
                metadata={"order_id": order.id, "status": order.status},
            )

            return Response(
                {"error": "La orden ya esta cerrada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not order.can_be_cancelled():
            log_event(
                "order_cancel_failed",
                "Cancelacion rechazada por estado no cancelable.",
                request=request,
                severity="warning",
                metadata={"order_id": order.id, "status": order.status},
            )

            return Response(
                {"error": "Solo puedes cancelar pedidos pendientes o pagados"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if order.should_restore_stock_on_cancel():
            order.restore_items_stock()
            restored_stock = True

        order.status = "cancelado"
        order.completed = False
        order.save(update_fields=["status", "completed"])

    log_event(
        "order_cancel_success",
        "Orden cancelada correctamente.",
        request=request,
        metadata={"order_id": order.id, "restored_stock": restored_stock},
    )

    return Response(
        {"message": f"Orden #{order.id} cancelada correctamente"},
        status=status.HTTP_200_OK
    )
