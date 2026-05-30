"""
Archivo: serializers.py
Descripcion: Define los serializadores usados para convertir modelos y datos de usuario en estructuras JSON para la API.
Dependencias: Django REST Framework, modelo User y modelo Product
"""

from django.contrib.auth.models import User

from rest_framework import serializers

from .models import Customer, Product


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

    def validate_username(self, value):
        """
        Nombre: validate_username
        Descripcion: Normaliza el nombre de usuario antes de crear la cuenta.
        Retorna: Nombre de usuario sin espacios externos.
        """
        username = value.strip()

        if not username:
            raise serializers.ValidationError("El nombre de usuario es obligatorio.")

        return username

    def validate_email(self, value):
        """
        Nombre: validate_email
        Descripcion: Valida que el correo no exista en usuarios ni clientes.
        Retorna: Correo normalizado en minusculas.
        """
        email = value.strip().lower()

        if not email:
            raise serializers.ValidationError("El correo es obligatorio.")

        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Este correo ya esta registrado.")

        if Customer.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Este correo ya esta asociado a un cliente.")

        return email

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
