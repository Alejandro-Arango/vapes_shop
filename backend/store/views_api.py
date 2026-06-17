from django.core.cache import cache
from django.db import DatabaseError, connection
from django.db.models import Avg, Count, Q

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Category, FavoriteProduct, Product
from .serializers import CategorySerializer, ProductSerializer


PRODUCT_STOCK_FILTERS = ("all", "available", "low", "empty")
PRODUCT_DEFAULT_PAGE = 1
PRODUCT_DEFAULT_PAGE_SIZE = 6
PRODUCT_MAX_PAGE_SIZE = 24
HEALTH_CACHE_KEY = "store:health-check"
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
    page = request.query_params.get("page")
    page_size = request.query_params.get("page_size")

    if stock_filter not in PRODUCT_STOCK_FILTERS:
        return "Filtro de disponibilidad invalido."

    if ordering not in PRODUCT_ORDERING_OPTIONS:
        return "Ordenamiento invalido."

    if page is not None and not page.strip().isdigit():
        return "Pagina invalida."

    if page is not None and int(page) < 1:
        return "Pagina invalida."

    if page_size is not None and not page_size.strip().isdigit():
        return "Tamano de pagina invalido."

    if page_size is not None:
        clean_page_size = int(page_size)

        if clean_page_size < 1 or clean_page_size > PRODUCT_MAX_PAGE_SIZE:
            return "Tamano de pagina invalido."

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


def should_paginate_products(request):
    """
    Nombre: should_paginate_products
    Descripcion: Determina si el cliente pidio respuesta paginada.
    """
    return "page" in request.query_params or "page_size" in request.query_params


def get_product_pagination_params(request):
    """
    Nombre: get_product_pagination_params
    Descripcion: Obtiene pagina y tamano de pagina con valores por defecto seguros.
    """
    page = int(request.query_params.get("page", PRODUCT_DEFAULT_PAGE))
    page_size = int(request.query_params.get("page_size", PRODUCT_DEFAULT_PAGE_SIZE))

    return page, page_size


def paginate_products(products, request):
    """
    Nombre: paginate_products
    Descripcion: Recorta el queryset y agrega metadatos para navegar el catalogo.
    """
    page, page_size = get_product_pagination_params(request)
    total = products.count()
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    end = start + page_size

    pagination = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1 and total_pages > 0,
    }

    return products[start:end], pagination


def get_user_favorite_product_ids(request, products):
    """
    Nombre: get_user_favorite_product_ids
    Descripcion: Obtiene los IDs favoritos del usuario para los productos entregados.
    """
    if not request.user.is_authenticated:
        return set()

    product_ids = [
        product.id
        for product in products
    ]

    if not product_ids:
        return set()

    return set(
        FavoriteProduct.objects.filter(
            user=request.user,
            product_id__in=product_ids,
        ).values_list("product_id", flat=True)
    )


def apply_private_cache_headers(response, request):
    """
    Nombre: apply_private_cache_headers
    Descripcion: Evita cachear respuestas de catalogo que incluyen estado del usuario.
    """
    if request.user.is_authenticated:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


def is_cache_available():
    """
    Nombre: is_cache_available
    Descripcion: Verifica lectura y escritura basica del cache configurado.
    """
    marker = "ok"

    try:
        cache.set(HEALTH_CACHE_KEY, marker, timeout=5)
        return cache.get(HEALTH_CACHE_KEY) == marker
    except Exception:
        return False


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Nombre: health_check
    Descripcion: Verifica que la aplicacion, base de datos y cache respondan.
    """
    try:
        connection.ensure_connection()
    except DatabaseError:
        return Response(
            {
                "status": "error",
                "database": "unavailable",
                "cache": "not_checked",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if not is_cache_available():
        return Response(
            {
                "status": "error",
                "database": "available",
                "cache": "unavailable",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {
            "status": "ok",
            "database": "available",
            "cache": "available",
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
        .annotate(
            rating_average=Avg(
                "reviews__rating",
                filter=Q(reviews__is_approved=True),
            ),
            rating_count=Count(
                "reviews",
                filter=Q(reviews__is_approved=True),
            ),
        )
    )
    products = apply_product_query_params(products, request)

    if should_paginate_products(request):
        products, pagination = paginate_products(products, request)
        products = list(products)
        favorite_product_ids = get_user_favorite_product_ids(request, products)
        serializer = ProductSerializer(
            products,
            many=True,
            context={"favorite_product_ids": favorite_product_ids},
        )

        response = Response(
            {
                "results": serializer.data,
                "pagination": pagination,
            }
        )

        return apply_private_cache_headers(response, request)

    products = list(products)
    favorite_product_ids = get_user_favorite_product_ids(request, products)
    serializer = ProductSerializer(
        products,
        many=True,
        context={"favorite_product_ids": favorite_product_ids},
    )

    response = Response(serializer.data)

    return apply_private_cache_headers(response, request)


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
