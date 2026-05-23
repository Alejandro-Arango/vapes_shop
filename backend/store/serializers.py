"""
Archivo: serializers.py
Descripcion: Define los serializadores usados para convertir modelos y datos de usuario en estructuras JSON para la API.
Dependencias: Django REST Framework, modelo User y modelo Product
"""

from django.contrib.auth.models import User

from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    """
    Nombre: ProductSerializer
    Descripcion: Convierte los datos del modelo Product en formato JSON para la API.
    """

    class Meta:
        model = Product
        fields = "__all__"


class UserRegisterSerializer(serializers.ModelSerializer):
    """
    Nombre: UserRegisterSerializer
    Descripcion: Valida los datos de registro y crea usuarios usando el sistema de autenticacion de Django.
    """

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def create(self, validated_data):
        """
        Nombre: create
        Descripcion: Crea un usuario nuevo usando create_user para guardar la contrasena de forma segura.
        """
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )


class UserSerializer(serializers.ModelSerializer):
    """
    Nombre: UserSerializer
    Descripcion: Expone datos basicos del usuario autenticado.
    """

    class Meta:
        model = User
        fields = ("id", "username", "email")