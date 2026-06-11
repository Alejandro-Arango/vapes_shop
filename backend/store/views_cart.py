"""
Archivo: views_cart.py
Descripcion: Gestiona las operaciones del carrito usando la sesion de Django.
Dependencias: Django REST Framework, modelo Product
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .cart_utils import parse_positive_quantity, sync_cart_with_products
from .models import Product


@api_view(["GET"])
def api_cart(request):
    """
    Nombre: api_cart
    Descripcion: Devuelve el carrito almacenado en la sesion de Django con productos, cantidades y total.
    """
    cart = request.session.get("cart", {})
    synced_cart, cart_items, cart_changed = sync_cart_with_products(cart)

    if cart_changed:
        request.session["cart"] = synced_cart
        request.session.modified = True

    items = []

    for item in cart_items:
        product = item["product"]

        items.append({
            "product": {
                "id": product.id,
                "name": product.name,
                "price": float(product.price),
                "image": product.image.url if product.image else "",
                "stock": product.stock,
            },
            "quantity": item["quantity"],
        })

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

    product_id = str(data.get("productId", "")).strip()
    quantity = parse_positive_quantity(data.get("quantity", 1))

    if not product_id.isdigit():
        return Response({"error": "productId invalido"}, status=400)

    if quantity is None:
        return Response({"error": "Cantidad invalida"}, status=400)

    try:
        product = Product.objects.get(id=int(product_id), is_active=True)
    except Product.DoesNotExist:
        return Response({"error": "Producto no disponible"}, status=404)

    if product.stock <= 0:
        return Response({"error": "Producto sin stock"}, status=400)

    product_id = str(product.id)
    cart = request.session.get("cart", {})

    current_quantity = parse_positive_quantity(cart.get(product_id, 0)) or 0
    new_quantity = current_quantity + quantity

    if new_quantity > product.stock:
        return Response(
            {"error": f"Stock insuficiente para {product.name}"},
            status=400
        )

    cart[product_id] = new_quantity

    request.session["cart"] = cart
    request.session.modified = True

    return Response({
        "ok": True,
        "cart": cart,
    })


@api_view(["POST"])
def api_cart_remove(request):
    """
    Nombre: api_cart_remove
    Descripcion: Elimina completamente un producto del carrito.
    """
    product_id = str(request.data.get("productId", "")).strip()

    if not product_id.isdigit():
        return Response({"error": "productId invalido"}, status=400)

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
    product_id = str(request.data.get("productId", "")).strip()

    if not product_id.isdigit():
        return Response({"error": "productId invalido"}, status=400)

    cart = request.session.get("cart", {})

    if product_id in cart:
        current_quantity = parse_positive_quantity(cart.get(product_id))

        if current_quantity is None:
            cart.pop(product_id, None)
        else:
            cart[product_id] = current_quantity - 1

            if cart[product_id] <= 0:
                cart.pop(product_id, None)

    request.session["cart"] = cart
    request.session.modified = True

    return Response({
        "ok": True,
        "cart": cart,
    })

@api_view(["POST"])
def api_cart_clear(request):
    """
    Nombre: api_cart_clear
    Descripcion: Elimina todos los productos almacenados en el carrito de la sesion.
    """
    request.session["cart"] = {}
    request.session.modified = True

    return Response({
        "ok": True,
        "message": "Carrito vaciado correctamente",
    })
