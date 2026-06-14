"""
Archivo: discounts.py
Descripcion: Utilidades para validar cupones y calcular totales de carrito y checkout.
Dependencias: Decimal, timezone de Django y modelo DiscountCode
"""

from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from .models import DiscountCode


COUPON_SESSION_KEY = "coupon_code"
MONEY_QUANT = Decimal("0.01")


def normalize_coupon_code(value):
    """
    Nombre: normalize_coupon_code
    Descripcion: Normaliza codigos de cupon evitando espacios y variaciones de mayusculas.
    """
    return str(value or "").strip().upper()


def quantize_money(value):
    """
    Nombre: quantize_money
    Descripcion: Redondea valores monetarios a dos decimales.
    """
    return Decimal(value or 0).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def get_discount_subtotal(cart_items):
    """
    Nombre: get_discount_subtotal
    Descripcion: Calcula subtotal decimal desde items sincronizados del carrito.
    """
    subtotal = Decimal("0.00")

    for item in cart_items:
        subtotal += item["product"].price * Decimal(item["quantity"])

    return quantize_money(subtotal)


def get_discount_code(code, subtotal, lock=False):
    """
    Nombre: get_discount_code
    Descripcion: Valida existencia, vigencia, uso y minimo de compra de un cupon.
    """
    normalized_code = normalize_coupon_code(code)

    if not normalized_code:
        return None, ""

    queryset = DiscountCode.objects

    if lock:
        queryset = queryset.select_for_update()

    try:
        discount = queryset.get(code__iexact=normalized_code, is_active=True)
    except DiscountCode.DoesNotExist:
        return None, "Cupon no valido."

    now = timezone.now()

    if discount.starts_at and discount.starts_at > now:
        return None, "Cupon no disponible todavia."

    if discount.ends_at and discount.ends_at < now:
        return None, "Cupon vencido."

    if discount.max_uses is not None and discount.used_count >= discount.max_uses:
        return None, "Cupon agotado."

    if subtotal < discount.min_order_total:
        minimum = quantize_money(discount.min_order_total)

        return None, f"Este cupon requiere una compra minima de ${minimum}."

    return discount, ""


def calculate_discount_amount(discount, subtotal):
    """
    Nombre: calculate_discount_amount
    Descripcion: Calcula el descuento segun tipo porcentaje o valor fijo.
    """
    if not discount:
        return Decimal("0.00")

    if discount.discount_type == "percent":
        amount = subtotal * (discount.value / Decimal("100"))
    else:
        amount = discount.value

    return min(quantize_money(amount), subtotal)


def build_pricing(subtotal, coupon_code="", lock=False):
    """
    Nombre: build_pricing
    Descripcion: Construye subtotal, descuento, total y datos publicos del cupon.
    """
    subtotal = quantize_money(subtotal)
    discount, coupon_error = get_discount_code(coupon_code, subtotal, lock=lock)
    discount_amount = calculate_discount_amount(discount, subtotal)
    total = quantize_money(subtotal - discount_amount)
    coupon_payload = None

    if discount:
        coupon_payload = {
            "code": discount.code,
            "description": discount.description,
            "discount_type": discount.discount_type,
            "value": float(discount.value),
        }

    return {
        "subtotal": subtotal,
        "discount": discount_amount,
        "total": total,
        "coupon": coupon_payload,
        "coupon_error": coupon_error,
        "discount_obj": discount,
    }


def pricing_response_payload(pricing):
    """
    Nombre: pricing_response_payload
    Descripcion: Convierte datos internos de pricing a respuesta JSON segura.
    """
    return {
        "subtotal": float(pricing["subtotal"]),
        "discount": float(pricing["discount"]),
        "total": float(pricing["total"]),
        "coupon": pricing["coupon"],
        "coupon_error": pricing["coupon_error"],
    }
