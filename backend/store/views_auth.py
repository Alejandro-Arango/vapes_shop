"""
Archivo: views_auth.py
Descripcion: Gestiona registro, inicio de sesion, cierre de sesion y consulta del usuario autenticado.
Dependencias: Django auth, modelo User, Django REST Framework, serializers de usuario y modelo Customer
"""

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    login,
    logout,
    password_validation,
    update_session_auth_hash,
)
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.utils.encoding import DjangoUnicodeDecodeError, force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .audit import log_event
from .customer_utils import ensure_customer_for_user
from .models import Order, ShippingAddress
from .serializers import (
    CustomerProfileSerializer,
    ShippingAddressSerializer,
    UserRegisterSerializer,
    UserSerializer,
)
from .throttles import AuthAnonRateThrottle, AuthUserRateThrottle


def get_customer_display_name(customer, user):
    """
    Nombre: get_customer_display_name
    Descripcion: Construye un nombre visible para autocompletar datos de envio.
    """
    full_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

    return full_name or user.username or user.email


def get_last_shipping_order(customer):
    """
    Nombre: get_last_shipping_order
    Descripcion: Busca el ultimo pedido con direccion registrada para sugerir datos de envio.
    """
    return (
        Order.objects
        .filter(customer=customer)
        .exclude(shipping_address__isnull=True)
        .exclude(shipping_address="")
        .order_by("-date_ordered", "-id")
        .first()
    )


def get_default_shipping_address(customer):
    """
    Nombre: get_default_shipping_address
    Descripcion: Obtiene la direccion guardada que debe sugerirse en checkout.
    """
    return customer.shipping_addresses.order_by("-is_default", "-updated_at", "-id").first()


def serialize_shipping_address_as_checkout(address):
    """
    Nombre: serialize_shipping_address_as_checkout
    Descripcion: Convierte una direccion guardada al formato usado por el checkout.
    """
    if not address:
        return {}

    return {
        "id": address.id,
        "label": address.label,
        "name": address.name,
        "phone": address.phone,
        "address": address.address,
        "city": address.city,
        "notes": address.notes,
    }


def ensure_single_default_shipping_address(address):
    """
    Nombre: ensure_single_default_shipping_address
    Descripcion: Mantiene una sola direccion predeterminada por cliente.
    """
    if not address.is_default:
        return address

    ShippingAddress.objects.filter(
        customer=address.customer,
        is_default=True,
    ).exclude(id=address.id).update(is_default=False)

    return address


def ensure_customer_has_default_shipping_address(customer):
    """
    Nombre: ensure_customer_has_default_shipping_address
    Descripcion: Promueve una direccion disponible si el cliente queda sin predeterminada.
    """
    if customer.shipping_addresses.filter(is_default=True).exists():
        return

    fallback = customer.shipping_addresses.order_by("-updated_at", "-id").first()

    if fallback:
        fallback.is_default = True
        fallback.save(update_fields=["is_default", "updated_at"])


def serialize_current_user(user):
    """
    Nombre: serialize_current_user
    Descripcion: Expone usuario, customer y datos sugeridos de envio para el checkout.
    """
    customer = ensure_customer_for_user(user)
    default_address = get_default_shipping_address(customer)
    last_order = get_last_shipping_order(customer)
    customer_name = get_customer_display_name(customer, user)

    default_shipping = {
        "id": None,
        "label": "",
        "name": customer_name,
        "phone": customer.phone or "",
        "address": "",
        "city": "",
        "notes": "",
    }

    if default_address:
        default_shipping.update(
            serialize_shipping_address_as_checkout(default_address)
        )
    elif last_order:
        default_shipping.update({
            "id": None,
            "label": "",
            "name": last_order.shipping_name or customer_name,
            "phone": last_order.shipping_phone or customer.phone or "",
            "address": last_order.shipping_address or "",
            "city": last_order.shipping_city or "",
            "notes": last_order.shipping_notes or "",
        })

    data = UserSerializer(user).data
    data["customer"] = {
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone or "",
    }
    data["default_shipping"] = default_shipping
    data["shipping_addresses"] = ShippingAddressSerializer(
        customer.shipping_addresses.all(),
        many=True,
    ).data

    return data


def normalize_login_identifier(data):
    """
    Nombre: normalize_login_identifier
    Descripcion: Normaliza el correo o usuario recibido en login sin asumir el tipo de dato.
    Retorna: Texto limpio o cadena vacia si no existe.
    """
    identifier = data.get("email") or data.get("username") or ""

    return str(identifier).strip()


def normalize_login_password(value):
    """
    Nombre: normalize_login_password
    Descripcion: Acepta solo contrasenas de texto para evitar errores con payloads mal formados.
    Retorna: Contrasena recibida o cadena vacia si el tipo no es valido.
    """
    if not isinstance(value, str):
        return ""

    return value


def normalize_reset_email(value):
    """
    Nombre: normalize_reset_email
    Descripcion: Normaliza el correo recibido para solicitar recuperacion de cuenta.
    Retorna: Correo en minusculas o cadena vacia si el dato no es texto.
    """
    if not isinstance(value, str):
        return ""

    return value.strip().lower()


def build_password_reset_url(request, user):
    """
    Nombre: build_password_reset_url
    Descripcion: Crea un enlace firmado para restablecer contrasena desde el frontend.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = f"/?reset_password=1&uid={uid}&token={token}"

    return request.build_absolute_uri(path)


def get_user_from_reset_token(uid, token):
    """
    Nombre: get_user_from_reset_token
    Descripcion: Valida uid y token de recuperacion sin exponer detalles al cliente.
    """
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id, is_active=True)
    except (
        TypeError,
        ValueError,
        OverflowError,
        DjangoUnicodeDecodeError,
        User.DoesNotExist,
    ):
        return None

    if not default_token_generator.check_token(user, token):
        return None

    return user


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonRateThrottle])
def register(request):
    """
    Nombre: register
    Descripcion: Crea un usuario nuevo, asegura su Customer asociado e inicia sesion automaticamente.
    """
    serializer = UserRegisterSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.save()

        ensure_customer_for_user(user)

        login(request, user)
        log_event(
            "auth_register_success",
            "Usuario registrado correctamente.",
            request=request,
            user=user,
            metadata={"user_id": user.id},
        )

        return Response(
            serialize_current_user(user),
            status=status.HTTP_201_CREATED
        )

    log_event(
        "auth_register_failed",
        "Registro rechazado por validaciones.",
        request=request,
        severity="warning",
        metadata={"errors": serializer.errors},
    )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonRateThrottle])
def login_view(request):
    """
    Nombre: login_view
    Descripcion: Inicia sesion usando nombre de usuario o correo electronico.
    """
    email_or_username = normalize_login_identifier(request.data)
    password = normalize_login_password(request.data.get("password"))

    if not email_or_username or not password:
        log_event(
            "auth_login_failed",
            "Intento de login con campos incompletos.",
            request=request,
            severity="warning",
        )

        return Response(
            {"error": "Faltan campos"},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = authenticate(
        request,
        username=email_or_username,
        password=password
    )

    if user is None:
        try:
            user_obj = User.objects.filter(
                email__iexact=email_or_username
            ).first()

            if user_obj is None:
                raise User.DoesNotExist

            user = authenticate(
                request,
                username=user_obj.username,
                password=password
            )

        except User.DoesNotExist:
            user = None

    if user is None:
        identifier_type = "email" if "@" in email_or_username else "username"

        log_event(
            "auth_login_failed",
            "Intento de login con credenciales invalidas.",
            request=request,
            severity="warning",
            metadata={"identifier_type": identifier_type},
        )

        return Response(
            {"error": "Credenciales invalidas"},
            status=status.HTTP_400_BAD_REQUEST
        )

    login(request, user)

    ensure_customer_for_user(user)
    log_event(
        "auth_login_success",
        "Usuario inicio sesion correctamente.",
        request=request,
        user=user,
        metadata={"user_id": user.id},
    )

    return Response(
        serialize_current_user(user),
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonRateThrottle])
def password_reset_request(request):
    """
    Nombre: password_reset_request
    Descripcion: Envia enlace de recuperacion sin revelar si el correo existe.
    """
    email = normalize_reset_email(request.data.get("email"))

    try:
        validate_email(email)
    except DjangoValidationError:
        log_event(
            "password_reset_request_invalid",
            "Solicitud de recuperacion con correo invalido.",
            request=request,
            severity="warning",
        )

        return Response(
            {"error": "Ingresa un correo valido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = User.objects.filter(email__iexact=email, is_active=True).first()
    response_data = {
        "message": (
            "Si el correo existe, enviaremos instrucciones para restablecer "
            "la contrasena."
        )
    }

    if user is None:
        log_event(
            "password_reset_requested",
            "Solicitud de recuperacion recibida para correo no registrado.",
            request=request,
            severity="info",
            metadata={"account_found": False},
        )

        return Response(response_data, status=status.HTTP_200_OK)

    reset_url = build_password_reset_url(request, user)
    email_sent = False

    try:
        email_sent = bool(
            send_mail(
                subject="Recupera tu cuenta de Vape Shop",
                message=(
                    "Recibimos una solicitud para restablecer tu contrasena.\n\n"
                    f"Usa este enlace para crear una nueva contrasena:\n{reset_url}\n\n"
                    "Si no solicitaste este cambio, puedes ignorar este mensaje."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        )
    except Exception as exc:
        log_event(
            "password_reset_email_failed",
            "No se pudo enviar el correo de recuperacion.",
            request=request,
            user=user,
            severity="error",
            metadata={"user_id": user.id, "error": exc.__class__.__name__},
        )

    log_event(
        "password_reset_requested",
        "Solicitud de recuperacion procesada.",
        request=request,
        user=user,
        metadata={"user_id": user.id, "email_sent": email_sent},
    )

    return Response(response_data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthAnonRateThrottle])
def password_reset_confirm(request):
    """
    Nombre: password_reset_confirm
    Descripcion: Valida token de recuperacion y guarda una nueva contrasena.
    """
    uid = str(request.data.get("uid") or "").strip()
    token = str(request.data.get("token") or "").strip()
    password = normalize_login_password(request.data.get("password"))
    password_confirm = normalize_login_password(request.data.get("password_confirm"))
    user = get_user_from_reset_token(uid, token)

    if user is None:
        log_event(
            "password_reset_confirm_failed",
            "Token de recuperacion invalido o vencido.",
            request=request,
            severity="warning",
        )

        return Response(
            {"error": "El enlace de recuperacion no es valido o ya expiro."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not password or password != password_confirm:
        log_event(
            "password_reset_confirm_failed",
            "Confirmacion de recuperacion con contrasenas invalidas.",
            request=request,
            user=user,
            severity="warning",
            metadata={"user_id": user.id},
        )

        return Response(
            {"error": "Las contrasenas no coinciden."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        log_event(
            "password_reset_confirm_failed",
            "Nueva contrasena rechazada por validaciones.",
            request=request,
            user=user,
            severity="warning",
            metadata={"user_id": user.id},
        )

        return Response(
            {"password": list(exc.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user.set_password(password)
    user.save(update_fields=["password"])

    log_event(
        "password_reset_confirmed",
        "Contrasena restablecida correctamente.",
        request=request,
        user=user,
        metadata={"user_id": user.id},
    )

    return Response(
        {"message": "Contrasena actualizada correctamente."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Nombre: logout_view
    Descripcion: Cierra la sesion activa del usuario autenticado.
    """
    log_event(
        "auth_logout",
        "Usuario cerro sesion.",
        request=request,
        user=request.user,
    )

    logout(request)

    return Response(
        {"message": "Logout exitoso"},
        status=status.HTTP_200_OK
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    Nombre: me
    Descripcion: Devuelve los datos del usuario autenticado actual.
    """
    return Response(
        serialize_current_user(request.user),
        status=status.HTTP_200_OK
    )


@api_view(["POST", "PATCH"])
@permission_classes([IsAuthenticated])
def profile(request):
    """
    Nombre: profile
    Descripcion: Actualiza datos basicos del cliente autenticado y devuelve el perfil vigente.
    """
    serializer = CustomerProfileSerializer(data=request.data)

    if not serializer.is_valid():
        log_event(
            "profile_update_failed",
            "Actualizacion de perfil rechazada por validaciones.",
            request=request,
            user=request.user,
            severity="warning",
            metadata={"errors": serializer.errors},
        )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    customer = ensure_customer_for_user(request.user)
    serializer.update_customer(customer)

    log_event(
        "profile_update_success",
        "Perfil de cliente actualizado.",
        request=request,
        user=request.user,
        metadata={"user_id": request.user.id},
    )

    return Response(
        serialize_current_user(request.user),
        status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([AuthUserRateThrottle])
def password_change(request):
    """
    Nombre: password_change
    Descripcion: Permite cambiar contrasena desde una sesion autenticada.
    """
    current_password = normalize_login_password(request.data.get("current_password"))
    new_password = normalize_login_password(request.data.get("new_password"))
    new_password_confirm = normalize_login_password(
        request.data.get("new_password_confirm")
    )

    if not current_password or not request.user.check_password(current_password):
        log_event(
            "password_change_failed",
            "Cambio de contrasena rechazado por contrasena actual invalida.",
            request=request,
            user=request.user,
            severity="warning",
            metadata={"reason": "invalid_current_password"},
        )

        return Response(
            {"error": "La contrasena actual no es correcta."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not new_password or new_password != new_password_confirm:
        log_event(
            "password_change_failed",
            "Cambio de contrasena rechazado por confirmacion invalida.",
            request=request,
            user=request.user,
            severity="warning",
            metadata={"reason": "password_mismatch"},
        )

        return Response(
            {"error": "Las contrasenas nuevas no coinciden."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        password_validation.validate_password(new_password, request.user)
    except DjangoValidationError as exc:
        log_event(
            "password_change_failed",
            "Cambio de contrasena rechazado por validaciones.",
            request=request,
            user=request.user,
            severity="warning",
            metadata={"reason": "weak_password"},
        )

        return Response(
            {"password": list(exc.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    request.user.set_password(new_password)
    request.user.save(update_fields=["password"])
    update_session_auth_hash(request, request.user)

    log_event(
        "password_change_success",
        "Contrasena actualizada desde perfil.",
        request=request,
        user=request.user,
        metadata={"user_id": request.user.id},
    )

    return Response(
        {"message": "Contrasena actualizada correctamente."},
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def shipping_addresses(request):
    """
    Nombre: shipping_addresses
    Descripcion: Lista o crea direcciones de envio guardadas para el cliente autenticado.
    """
    customer = ensure_customer_for_user(request.user)

    if request.method == "GET":
        return Response(
            serialize_current_user(request.user),
            status=status.HTTP_200_OK
        )

    serializer = ShippingAddressSerializer(data=request.data)

    if not serializer.is_valid():
        log_event(
            "shipping_address_save_failed",
            "Direccion de envio rechazada por validaciones.",
            request=request,
            user=request.user,
            severity="warning",
            metadata={"errors": serializer.errors},
        )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        is_first_address = not customer.shipping_addresses.exists()
        address = serializer.save(customer=customer)

        if is_first_address:
            address.is_default = True
            address.save(update_fields=["is_default", "updated_at"])

        ensure_single_default_shipping_address(address)
        ensure_customer_has_default_shipping_address(customer)

    log_event(
        "shipping_address_saved",
        "Direccion de envio guardada.",
        request=request,
        user=request.user,
        metadata={"shipping_address_id": address.id},
    )

    data = serialize_current_user(request.user)
    data["saved_shipping_address_id"] = address.id

    return Response(data, status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def shipping_address_detail(request, address_id):
    """
    Nombre: shipping_address_detail
    Descripcion: Actualiza o elimina una direccion guardada del cliente autenticado.
    """
    customer = ensure_customer_for_user(request.user)

    try:
        address = ShippingAddress.objects.get(id=address_id, customer=customer)
    except ShippingAddress.DoesNotExist:
        return Response(
            {"error": "Direccion de envio no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "DELETE":
        deleted_address_id = address.id

        with transaction.atomic():
            address.delete()
            ensure_customer_has_default_shipping_address(customer)

        log_event(
            "shipping_address_deleted",
            "Direccion de envio eliminada.",
            request=request,
            user=request.user,
            metadata={"shipping_address_id": deleted_address_id},
        )

        return Response(
            serialize_current_user(request.user),
            status=status.HTTP_200_OK
        )

    serializer = ShippingAddressSerializer(
        address,
        data=request.data,
        partial=True,
    )

    if not serializer.is_valid():
        log_event(
            "shipping_address_update_failed",
            "Actualizacion de direccion rechazada por validaciones.",
            request=request,
            user=request.user,
            severity="warning",
            metadata={"errors": serializer.errors},
        )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        address = serializer.save()
        ensure_single_default_shipping_address(address)
        ensure_customer_has_default_shipping_address(customer)

    log_event(
        "shipping_address_updated",
        "Direccion de envio actualizada.",
        request=request,
        user=request.user,
        metadata={"shipping_address_id": address.id},
    )

    data = serialize_current_user(request.user)
    data["saved_shipping_address_id"] = address.id

    return Response(data, status=status.HTTP_200_OK)
