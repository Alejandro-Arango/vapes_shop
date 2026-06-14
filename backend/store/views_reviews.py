"""
Archivo: views_reviews.py
Descripcion: Gestiona reseñas y calificaciones de productos.
Dependencias: Django ORM, Django REST Framework, auditoria y modelos de store
"""

from django.db.models import Avg, Count

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .audit import log_event
from .models import Product, ProductReview


REVIEW_COMMENT_MAX_LENGTH = 600


def apply_no_store(response):
    """
    Nombre: apply_no_store
    Descripcion: Evita cachear reseñas porque pueden incluir estado del usuario actual.
    """
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


def get_review_summary(product):
    """
    Nombre: get_review_summary
    Descripcion: Calcula promedio y cantidad de reseñas aprobadas de un producto.
    """
    summary = ProductReview.objects.filter(
        product=product,
        is_approved=True,
    ).aggregate(
        rating_average=Avg("rating"),
        rating_count=Count("id"),
    )

    return {
        "rating_average": round(float(summary["rating_average"] or 0), 1),
        "rating_count": int(summary["rating_count"] or 0),
    }


def serialize_review(review, request):
    """
    Nombre: serialize_review
    Descripcion: Convierte una reseña en datos seguros para el frontend.
    """
    return {
        "id": review.id,
        "rating": review.rating,
        "comment": review.comment,
        "user": review.user.username or review.user.email,
        "owned_by_user": (
            request.user.is_authenticated and review.user_id == request.user.id
        ),
        "created_at": review.created_at,
        "updated_at": review.updated_at,
    }


def parse_review_payload(data):
    """
    Nombre: parse_review_payload
    Descripcion: Valida rating y comentario recibidos desde el frontend.
    Retorna: Tupla de datos limpios y mensaje de error.
    """
    raw_rating = data.get("rating")
    raw_comment = data.get("comment", "")

    if isinstance(raw_rating, bool):
        return None, None, "La calificacion no es valida."

    try:
        rating = int(raw_rating)
    except (TypeError, ValueError):
        return None, None, "La calificacion no es valida."

    if rating < 1 or rating > 5:
        return None, None, "La calificacion debe estar entre 1 y 5."

    if not isinstance(raw_comment, str):
        return None, None, "El comentario no es valido."

    comment = raw_comment.strip()

    if len(comment) > REVIEW_COMMENT_MAX_LENGTH:
        return None, None, "El comentario no puede superar 600 caracteres."

    return rating, comment, ""


def get_active_product_or_response(product_id):
    """
    Nombre: get_active_product_or_response
    Descripcion: Obtiene un producto activo o retorna una respuesta 404.
    """
    try:
        return Product.objects.get(id=product_id, is_active=True), None
    except Product.DoesNotExist:
        response = Response(
            {"error": "Producto no encontrado"},
            status=status.HTTP_404_NOT_FOUND,
        )

        return None, apply_no_store(response)


@api_view(["GET"])
@permission_classes([AllowAny])
def product_reviews(request, product_id):
    """
    Nombre: product_reviews
    Descripcion: Devuelve reseñas aprobadas y resumen de calificacion de un producto.
    """
    product, error_response = get_active_product_or_response(product_id)

    if error_response:
        return error_response

    reviews = (
        ProductReview.objects
        .filter(product=product, is_approved=True)
        .select_related("user")
        .order_by("-created_at")
    )
    own_review = None

    if request.user.is_authenticated:
        own_review = reviews.filter(user=request.user).first()

    response = Response(
        {
            "product_id": product.id,
            **get_review_summary(product),
            "own_review": (
                serialize_review(own_review, request)
                if own_review
                else None
            ),
            "reviews": [
                serialize_review(review, request)
                for review in reviews[:10]
            ],
        },
        status=status.HTTP_200_OK,
    )

    return apply_no_store(response)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_product_review(request, product_id):
    """
    Nombre: submit_product_review
    Descripcion: Crea o actualiza la reseña del usuario sobre un producto activo.
    """
    product, error_response = get_active_product_or_response(product_id)

    if error_response:
        return error_response

    rating, comment, payload_error = parse_review_payload(request.data)

    if payload_error:
        return apply_no_store(
            Response(
                {"error": payload_error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        )

    review, created = ProductReview.objects.update_or_create(
        user=request.user,
        product=product,
        defaults={
            "rating": rating,
            "comment": comment,
            "is_approved": True,
        },
    )
    event_type = "review_created" if created else "review_updated"

    log_event(
        event_type,
        "Reseña de producto registrada.",
        request=request,
        user=request.user,
        metadata={
            "product_id": product.id,
            "rating": rating,
        },
    )

    response = Response(
        {
            "review": serialize_review(review, request),
            **get_review_summary(product),
            "message": "Reseña guardada correctamente.",
        },
        status=status.HTTP_200_OK,
    )

    return apply_no_store(response)
