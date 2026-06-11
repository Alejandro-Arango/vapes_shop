"""
Archivo: cart_utils.py
Descripcion: Utilidades compartidas para validar y sincronizar el carrito con el catalogo actual.
Dependencias: Modelo Product
"""

from .models import Product


def parse_positive_quantity(value):
    """
    Nombre: parse_positive_quantity
    Descripcion: Convierte una cantidad recibida desde la API en entero positivo.
    Retorna: Cantidad valida o None si el valor no es aceptable.
    """
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return None

    if quantity <= 0:
        return None

    return quantity


def sync_cart_with_products(cart):
    """
    Nombre: sync_cart_with_products
    Descripcion: Elimina productos no disponibles y ajusta cantidades segun el stock actual.
    Retorna: Carrito sincronizado, items validos y bandera de cambios.
    """
    synced_cart = {}
    items = []
    cart_changed = False

    for pid, qty in list(cart.items()):
        try:
            product_id = int(pid)
        except (TypeError, ValueError):
            cart_changed = True
            continue

        quantity = parse_positive_quantity(qty)

        if quantity is None:
            cart_changed = True
            continue

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            cart_changed = True
            continue

        if product.stock <= 0:
            cart_changed = True
            continue

        if quantity > product.stock:
            quantity = product.stock
            cart_changed = True

        synced_cart[str(product.id)] = quantity
        items.append({
            "product": product,
            "quantity": quantity,
        })

    return synced_cart, items, cart_changed
