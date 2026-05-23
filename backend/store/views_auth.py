"""
Archivo: views_auth.py
Descripcion: Gestiona registro, inicio de sesion, cierre de sesion y consulta del usuario autenticado.
Dependencias: Django auth, modelo User, Django REST Framework, serializers de usuario y modelo Customer
"""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import Customer
from .serializers import UserRegisterSerializer, UserSerializer


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

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    """
    Nombre: login_view
    Descripcion: Inicia sesion usando nombre de usuario o correo electronico.
    """
    email_or_username = request.data.get("email") or request.data.get("username")
    password = request.data.get("password")

    if not email_or_username or not password:
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
            user_obj = User.objects.get(email=email_or_username)

            user = authenticate(
                request,
                username=user_obj.username,
                password=password
            )

        except User.DoesNotExist:
            user = None

    if user is None:
        return Response(
            {"error": "Credenciales invalidas"},
            status=status.HTTP_400_BAD_REQUEST
        )

    login(request, user)

    ensure_customer_for_user(user)

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