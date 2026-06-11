"""
Archivo: customer_utils.py
Descripcion: Centraliza utilidades para asociar usuarios autenticados con clientes de la tienda.
Dependencias: modelo User de Django y modelo Customer
"""

from django.contrib.auth.models import User

from .models import Customer


def ensure_customer_for_user(user: User) -> Customer:
    """
    Nombre: ensure_customer_for_user
    Descripcion: Asegura que exista un Customer asociado al usuario y reutiliza clientes sin usuario cuando coincide el correo.
    Retorna: Customer asociado al usuario.
    """
    email = (user.email or "").strip()

    try:
        customer = user.customer
        linked_existing_customer = False
    except Customer.DoesNotExist:
        customer = None
        linked_existing_customer = False

        if email:
            customer = Customer.objects.filter(
                user__isnull=True,
                email__iexact=email,
            ).first()

        if customer:
            customer.user = user
            linked_existing_customer = True
        else:
            return Customer.objects.create(
                user=user,
                email=email or f"{user.username}@example.com",
                first_name=user.first_name or user.username,
                last_name=user.last_name or "",
                phone="",
            )

    changed = linked_existing_customer

    if not customer.email and email:
        customer.email = email
        changed = True

    if not customer.first_name and user.first_name:
        customer.first_name = user.first_name
        changed = True

    if not customer.last_name and user.last_name:
        customer.last_name = user.last_name
        changed = True

    if customer.user_id != user.id:
        customer.user = user
        changed = True

    if changed:
        customer.save()

    return customer
