"""
Archivo: serializers.py
Descripcion: Define los serializadores usados para convertir modelos y datos de usuario en estructuras JSON para la API.
Dependencias: Django REST Framework, modelo User y modelos principales de store
"""

from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from .models import ContactLead, Customer, Product


class ProductSerializer(serializers.ModelSerializer):
    """
    Nombre: ProductSerializer
    Descripcion: Convierte los datos del modelo Product en formato JSON para la API.
    """

    class Meta:
        model = Product
        fields = "__all__"


class ContactLeadSerializer(serializers.ModelSerializer):
    """
    Nombre: ContactLeadSerializer
    Descripcion: Valida y registra correos enviados desde el formulario de contacto.
    """

    class Meta:
        model = ContactLead
        fields = (
            "id",
            "name",
            "email",
            "phone",
            "message",
            "status",
            "whatsapp_message",
            "email_notification_sent",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "whatsapp_message",
            "email_notification_sent",
            "created_at",
            "updated_at",
        )

    def validate_name(self, value):
        """
        Nombre: validate_name
        Descripcion: Normaliza el nombre enviado en el formulario de contacto.
        Retorna: Nombre sin espacios externos.
        """
        return value.strip()

    def validate_email(self, value):
        """
        Nombre: validate_email
        Descripcion: Normaliza el correo de contacto antes de guardarlo.
        Retorna: Correo normalizado en minusculas.
        """
        email = value.strip().lower()

        if not email:
            raise serializers.ValidationError("El correo es obligatorio.")

        return email

    def validate_phone(self, value):
        """
        Nombre: validate_phone
        Descripcion: Valida un telefono opcional evitando caracteres inesperados.
        Retorna: Telefono normalizado.
        """
        phone = value.strip()

        if not phone:
            return phone

        allowed_chars = set("0123456789+() -")

        if any(char not in allowed_chars for char in phone):
            raise serializers.ValidationError(
                "El telefono solo puede contener numeros, espacios, +, - y parentesis."
            )

        digits_count = sum(char.isdigit() for char in phone)

        if digits_count < 7:
            raise serializers.ValidationError("El telefono debe tener al menos 7 digitos.")

        return phone

    def validate_message(self, value):
        """
        Nombre: validate_message
        Descripcion: Normaliza el mensaje enviado desde contacto.
        Retorna: Mensaje sin espacios externos.
        """
        return value.strip()


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

        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("Este nombre de usuario ya esta registrado.")

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

    def validate_password(self, value):
        """
        Nombre: validate_password
        Descripcion: Aplica las reglas de seguridad de contrasena configuradas en Django.
        Retorna: Contrasena validada.
        """
        try:
            password_validation.validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))

        return value

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
