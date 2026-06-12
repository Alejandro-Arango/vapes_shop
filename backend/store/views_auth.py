"""
Archivo: views_auth.py
Descripcion: Gestiona registro, inicio de sesion, cierre de sesion y consulta del usuario autenticado.
Dependencias: Django auth, modelo User, Django REST Framework, serializers de usuario y modelo Customer
"""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .audit import log_event
from .customer_utils import ensure_customer_for_user
from .serializers import UserRegisterSerializer, UserSerializer
from .throttles import AuthAnonRateThrottle


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
            UserSerializer(user).data,
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
        UserSerializer(user).data,
        status=status.HTTP_200_OK
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
        UserSerializer(request.user).data,
        status=status.HTTP_200_OK
    )
