"""
Archivo: views_orders.py
Descripcion: Gestiona checkout, consulta de pedidos, detalle de orden y cancelacion de pedidos.
Dependencias: Django transaction, Django REST Framework, modelos Product, Customer, Order y OrderItem
"""

from django.db import transaction

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Product, Customer, Order, OrderItem


def serialize_order(order):
    """
    Nombre: serialize_order
    Descripcion: Convierte una orden en un diccionario con productos, total y datos de envio.
    """
    items = []
    total = 0.0

    for item in order.orderitem_set.all():
        line_total = float(item.product.price) * item.quantity
        total += line_total

        items.append({
            "product": {
                "id": item.product.id,
                "name": item.product.name,
                "price": float(item.product.price),
                "image": item.product.image.url if item.product.image else "",
                "stock": item.product.stock,
            },
            "quantity": item.quantity,
            "line_total": line_total,
        })

    return {
        "id": order.id,
        "date_ordered": order.date_ordered,
        "completed": order.completed,
        "status": order.status,
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def checkout(request):
    """
    Nombre: checkout
    Descripcion: Crea una orden usando el carrito almacenado en sesion, guarda datos de envio y descuenta el stock disponible.
    """
    cart = request.session.get("cart", {})

    if not cart:
        return Response(
            {"error": "Carrito vacio"},
            status=status.HTTP_400_BAD_REQUEST
        )

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

    if not shipping_name or not shipping_phone or not shipping_address or not shipping_city:
        return Response(
            {"error": "Debes completar los datos de envio"},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = request.user

    customer, created = Customer.objects.get_or_create(
        user=user,
        defaults={
            "email": user.email or f"{user.username}@example.com",
            "first_name": user.first_name or user.username,
            "last_name": user.last_name or "",
            "phone": "",
        },
    )

    changed = False

    if not customer.email and user.email:
        customer.email = user.email
        changed = True

    if not customer.first_name and user.first_name:
        customer.first_name = user.first_name
        changed = True

    if not customer.last_name and user.last_name:
        customer.last_name = user.last_name
        changed = True

    if changed:
        customer.save()

    try:
        product_ids = [int(pid) for pid in cart.keys()]
    except ValueError:
        return Response(
            {"error": "Carrito invalido"},
            status=status.HTTP_400_BAD_REQUEST
        )

    products = Product.objects.filter(id__in=product_ids)

    if not products.exists():
        return Response(
            {"error": "No hay productos validos en el carrito"},
            status=status.HTTP_400_BAD_REQUEST
        )

    product_map = {
        product.id: product
        for product in products
    }

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
            return Response(
                {"error": f"Stock insuficiente para {product.name}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_lines.append((product, qty))

    if not order_lines:
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
                return Response(
                    {"error": f"Producto no disponible: {product.name}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if locked_product.stock < qty:
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
        )

        total = 0.0

        for product, qty in order_lines:
            locked_product = locked_map[product.id]

            OrderItem.objects.create(
                order=order,
                product=locked_product,
                quantity=qty
            )

            total += float(locked_product.price) * qty

            locked_product.stock -= qty
            locked_product.save(update_fields=["stock"])

        request.session["cart"] = {}
        request.session.modified = True

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
    try:
        customer = request.user.customer
    except Customer.DoesNotExist:
        return Response(
            {"orders": []},
            status=status.HTTP_200_OK
        )

    user_orders = (
        Order.objects
        .filter(customer=customer)
        .prefetch_related("orderitem_set__product")
        .order_by("-date_ordered")
    )

    orders = [
        serialize_order(order)
        for order in user_orders
    ]

    return Response(
        {"orders": orders},
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
        return Response(
            {"error": "No existe un customer asociado a este usuario"},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        try:
            order = (
                Order.objects
                .select_for_update()
                .prefetch_related("orderitem_set__product")
                .get(id=order_id, customer=customer)
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Orden no encontrada"},
                status=status.HTTP_404_NOT_FOUND
            )

        if order.status == "cancelado":
            return Response(
                {"error": "La orden ya esta cancelada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not order.can_be_cancelled():
            return Response(
                {"error": "Solo puedes cancelar pedidos pendientes o pagados"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if order.should_restore_stock_on_cancel():
            order.restore_items_stock()

        order.status = "cancelado"
        order.completed = False
        order.save(update_fields=["status", "completed"])

    return Response(
        {"message": f"Orden #{order.id} cancelada correctamente"},
        status=status.HTTP_200_OK
    )
