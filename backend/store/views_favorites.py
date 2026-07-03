"""
Archivo: views_favorites.py
Descripcion: Gestiona favoritos de productos para usuarios autenticados.
Dependencias: Django REST Framework, auditoria y modelos de store
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Avg, Count, Q

from .audit import log_event
from .cart_utils import parse_product_id
from .models import FavoriteProduct, Product
from .serializers import ProductSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def favorite_products(request):
    """
    Nombre: favorite_products
    Descripcion: Devuelve los productos favoritos activos del usuario autenticado.
    """
    products = list(
        Product.objects
        .filter(
            is_active=True,
            favorited_by__user=request.user,
        )
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
        .order_by("-favorited_by__created_at")
    )
    favorite_product_ids = {
        product.id
        for product in products
    }
    serializer = ProductSerializer(
        products,
        many=True,
        context={"favorite_product_ids": favorite_product_ids},
    )

    return Response(
        {
            "favorites": serializer.data,
            "count": len(products),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def toggle_favorite_product(request):
    """
    Nombre: toggle_favorite_product
    Descripcion: Marca o desmarca un producto activo como favorito del usuario autenticado.
    """
    product_id = parse_product_id(
        request.data.get("productId") or request.data.get("product_id")
    )

    if product_id is None:
        return Response(
            {"error": "Producto invalido"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        product = Product.objects.get(id=product_id, is_active=True)
    except Product.DoesNotExist:
        log_event(
            "favorite_failed",
            "Favorito rechazado porque el producto no existe o esta inactivo.",
            request=request,
            severity="warning",
            metadata={"product_id": product_id},
        )

        return Response(
            {"error": "Producto no encontrado"},
            status=status.HTTP_404_NOT_FOUND,
        )

    favorite, created = FavoriteProduct.objects.get_or_create(
        user=request.user,
        product=product,
    )

    if created:
        event_type = "favorite_added"
        message = "Producto agregado a favoritos."
        is_favorite = True
    else:
        favorite.delete()
        event_type = "favorite_removed"
        message = "Producto removido de favoritos."
        is_favorite = False

    log_event(
        event_type,
        message,
        request=request,
        user=request.user,
        metadata={"product_id": product.id},
    )

    return Response(
        {
            "product_id": product.id,
            "is_favorite": is_favorite,
            "message": message,
        },
        status=status.HTTP_200_OK,
    )
