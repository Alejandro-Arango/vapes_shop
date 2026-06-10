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
from .models import Customer
from .serializers import UserRegisterSerializer, UserSerializer
from .throttles import AuthAnonRateThrottle


def ensure_customer_for_user(user: User) -> Customer:
    """
    Nombre: ensure_customer_for_user
    Descripcion: Asegura que exista un Customer asociado al usuario y completa datos basicos si faltan.
    """
    customer, created = Customer.objects.get_or_create(
        user=user,
        defaults={
            "email": user.email or f"{user.username}@example.com",
            "first_name": user.first_name or user.username,
            "last_name": user.last_name or "",
            "phone": "",
        }
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

    return customer


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
            metadata={"username": user.username, "email": user.email},
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
    email_or_username = (
        request.data.get("email")
        or request.data.get("username")
        or ""
    ).strip()
    password = request.data.get("password")

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
        log_event(
            "auth_login_failed",
            "Intento de login con credenciales invalidas.",
            request=request,
            severity="warning",
            metadata={"identifier": email_or_username},
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
        metadata={"username": user.username},
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
