"""
Archivo: views_cart.py
Descripcion: Gestiona las operaciones del carrito usando la sesion de Django.
Dependencias: Django REST Framework, modelo Product
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Product


@api_view(["GET"])
def api_cart(request):
    """
    Nombre: api_cart
    Descripcion: Devuelve el carrito almacenado en la sesion de Django con productos, cantidades y total.
    """
    cart = request.session.get("cart", {})
    items = []

    for pid, qty in cart.items():
        try:
            product = Product.objects.get(id=int(pid))

            items.append({
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "price": float(product.price),
                    "image": product.image.url if product.image else "",
                    "stock": product.stock,
                },
                "quantity": qty,
            })

        except Product.DoesNotExist:
            continue

    total = sum(
        item["product"]["price"] * item["quantity"]
        for item in items
    )

    return Response({
        "items": items,
        "total": total,
    })


@api_view(["POST"])
def api_cart_add(request):
    """
    Nombre: api_cart_add
    Descripcion: Agrega un producto al carrito o aumenta su cantidad si ya existe.
    """
    data = request.data

    product_id = str(data.get("productId"))
    quantity = int(data.get("quantity", 1))

    if not product_id.isdigit():
        return Response({"error": "productId invalido"}, status=400)

    cart = request.session.get("cart", {})

    cart[product_id] = cart.get(product_id, 0) + quantity

    request.session["cart"] = cart
    request.session.modified = True

    return Response({"ok": True})


@api_view(["POST"])
def api_cart_remove(request):
    """
    Nombre: api_cart_remove
    Descripcion: Elimina completamente un producto del carrito.
    """
    product_id = str(request.data.get("productId"))

    cart = request.session.get("cart", {})

    cart.pop(product_id, None)

    request.session["cart"] = cart
    request.session.modified = True

    return Response({"ok": True})


@api_view(["POST"])
def api_cart_decrease(request):
    """
    Nombre: api_cart_decrease
    Descripcion: Disminuye en una unidad la cantidad de un producto y lo elimina si llega a cero.
    """
    product_id = str(request.data.get("productId"))

    if not product_id.isdigit():
        return Response({"error": "productId invalido"}, status=400)

    cart = request.session.get("cart", {})

    if product_id in cart:
        cart[product_id] -= 1

        if cart[product_id] <= 0:
            cart.pop(product_id, None)

    request.session["cart"] = cart
    request.session.modified = True

    return Response({
        "ok": True,
        "cart": cart,
    })