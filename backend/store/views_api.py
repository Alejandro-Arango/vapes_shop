from django.db import DatabaseError, connection
from django.db.models import Q

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer


PRODUCT_STOCK_FILTERS = ("all", "available", "low", "empty")
PRODUCT_ORDERING_OPTIONS = {
    "default": ("-created_at", "-id"),
    "price-asc": ("price", "id"),
    "price-desc": ("-price", "id"),
    "stock-desc": ("-stock", "-created_at", "-id"),
    "name-asc": ("name", "id"),
}


def get_product_query_error(request):
    """
    Nombre: get_product_query_error
    Descripcion: Valida filtros recibidos por query params para evitar comportamientos ambiguos.
    """
    stock_filter = request.query_params.get("stock", "all").strip().lower()
    ordering = request.query_params.get("ordering", "default").strip().lower()

    if stock_filter not in PRODUCT_STOCK_FILTERS:
        return "Filtro de disponibilidad invalido."

    if ordering not in PRODUCT_ORDERING_OPTIONS:
        return "Ordenamiento invalido."

    return ""


def apply_product_query_params(products, request):
    """
    Nombre: apply_product_query_params
    Descripcion: Aplica busqueda, categoria, disponibilidad y ordenamiento a productos activos.
    """
    search_value = request.query_params.get("q", "").strip()
    category_slug = request.query_params.get("category", "").strip()
    stock_filter = request.query_params.get("stock", "all").strip().lower()
    ordering = request.query_params.get("ordering", "default").strip().lower()

    if search_value:
        products = products.filter(
            Q(name__icontains=search_value)
            | Q(description__icontains=search_value)
            | Q(category__name__icontains=search_value, category__is_active=True)
        )

    if category_slug:
        products = products.filter(
            category__slug=category_slug,
            category__is_active=True,
        )

    if stock_filter == "available":
        products = products.filter(stock__gt=0)
    elif stock_filter == "low":
        products = products.filter(stock__gt=0, stock__lte=3)
    elif stock_filter == "empty":
        products = products.filter(stock=0)

    return products.order_by(*PRODUCT_ORDERING_OPTIONS[ordering])


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
    query_error = get_product_query_error(request)

    if query_error:
        return Response(
            {"error": query_error},
            status=status.HTTP_400_BAD_REQUEST,
        )

    products = (
        Product.objects
        .filter(is_active=True)
        .select_related("category")
    )
    products = apply_product_query_params(products, request)

    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def api_categories(request):
    """
    Nombre: api_categories
    Descripcion: Devuelve categorias activas para filtrar el catalogo del frontend.
    """
    categories = Category.objects.filter(is_active=True).order_by("name", "id")
    serializer = CategorySerializer(categories, many=True)

    return Response(serializer.data)
