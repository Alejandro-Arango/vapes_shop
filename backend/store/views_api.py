from django.db import DatabaseError, connection

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Product
from .serializers import ProductSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Nombre: health_check
    Descripcion: Verifica que la aplicacion y la base de datos respondan.
    """
    try:
        connection.ensure_connection()
    except DatabaseError:
        return Response(
            {
                "status": "error",
                "database": "unavailable",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {
            "status": "ok",
            "database": "available",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def api_products(request):
    """
    Devuelve la lista de productos en formato JSON para el frontend.
    Usa el serializer de Product. Si en el futuro agregas imagen al producto,
    se podrá incluir ahí.
    """
    products = Product.objects.filter(is_active=True).order_by("-created_at", "-id")
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)
