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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def checkout(request):
    """
    Nombre: checkout
    Descripcion: Crea una orden usando el carrito almacenado en sesion y descuenta el stock disponible.
    """
    cart = request.session.get("cart", {})

    if not cart:
        return Response(
            {"error": "Carrito vacio"},
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

    if (not customer.email) and user.email:
        customer.email = user.email
        changed = True

    if (not customer.first_name) and user.first_name:
        customer.first_name = user.first_name
        changed = True

    if (not customer.last_name) and user.last_name:
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
            status=status.HTTP_400_BAD_REQUEST,
        )

    product_map = {product.id: product for product in products}
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
                status=status.HTTP_400_BAD_REQUEST,
            )

        order_lines.append((product, qty))

    if not order_lines:
        return Response(
            {"error": "No se pudo procesar el carrito"},
            status=status.HTTP_400_BAD_REQUEST,
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
            locked_product = locked_map[product.id]

            if locked_product.stock < qty:
                return Response(
                    {"error": f"Stock insuficiente para {locked_product.name}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        order = Order.objects.create(
            customer=customer,
            completed=True,
            status="pagado",
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
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    """
    Nombre: my_orders
    Descripcion: Devuelve el historial de pedidos del usuario autenticado con sus productos y totales.
    """
    user = request.user

    try:
        customer = Customer.objects.get(user=user)
    except Customer.DoesNotExist:
        return Response(
            {"orders": []},
            status=status.HTTP_200_OK
        )

    orders_qs = (
        Order.objects
        .filter(customer=customer)
        .order_by("-date_ordered")
        .prefetch_related("orderitem_set__product")
    )

    orders = []

    for order in orders_qs:
        items = []
        total = 0.0

        for item in order.orderitem_set.all():
            price = float(item.product.price)
            line_total = price * item.quantity
            total += line_total

            items.append({
                "product": {
                    "id": item.product.id,
                    "name": item.product.name,
                    "price": price,
                    "image": item.product.image.url if item.product.image else "",
                },
                "quantity": item.quantity,
                "line_total": line_total,
            })

        orders.append({
            "id": order.id,
            "date_ordered": order.date_ordered,
            "completed": order.completed,
            "status": order.status,
            "total": total,
            "items": items,
        })

    return Response(
        {"orders": orders},
        status=status.HTTP_200_OK
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_detail(request, order_id):
    """
    Nombre: order_detail
    Descripcion: Devuelve el detalle de una orden especifica si pertenece al usuario autenticado.
    """
    user = request.user

    try:
        customer = Customer.objects.get(user=user)
    except Customer.DoesNotExist:
        return Response(
            {"error": "No existe un customer asociado a este usuario"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        order = Order.objects.prefetch_related("orderitem_set__product").get(
            id=order_id,
            customer=customer
        )
    except Order.DoesNotExist:
        return Response(
            {"error": "Orden no encontrada"},
            status=status.HTTP_404_NOT_FOUND
        )

    items = []
    total = 0.0

    for item in order.orderitem_set.all():
        price = float(item.product.price)
        line_total = price * item.quantity
        total += line_total

        items.append({
            "product": {
                "id": item.product.id,
                "name": item.product.name,
                "price": price,
                "image": item.product.image.url if item.product.image else "",
            },
            "quantity": item.quantity,
            "line_total": line_total,
        })

    return Response(
        {
            "id": order.id,
            "date_ordered": order.date_ordered,
            "completed": order.completed,
            "status": order.status,
            "total": total,
            "items": items,
        },
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_id):
    """
    Nombre: cancel_order
    Descripcion: Cancela una orden del usuario autenticado y devuelve el stock de sus productos.
    """
    user = request.user

    try:
        customer = Customer.objects.get(user=user)
    except Customer.DoesNotExist:
        return Response(
            {"error": "No existe un customer asociado a este usuario"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        order = Order.objects.prefetch_related("orderitem_set__product").get(
            id=order_id,
            customer=customer
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

    with transaction.atomic():
        for item in order.orderitem_set.all():
            product = item.product
            product.stock += item.quantity
            product.save(update_fields=["stock"])

        order.status = "cancelado"
        order.completed = False
        order.save(update_fields=["status", "completed"])

    return Response(
        {"message": f"Orden #{order.id} cancelada correctamente"},
        status=status.HTTP_200_OK
    )