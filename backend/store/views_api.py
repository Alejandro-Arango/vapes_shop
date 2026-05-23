from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Product
from .serializers import ProductSerializer


@api_view(["GET"])
def api_products(request):
    """
    Devuelve la lista de productos en formato JSON para el frontend.
    Usa el serializer de Product. Si en el futuro agregas imagen al producto,
    se podrá incluir ahí.
    """
    products = Product.objects.all()
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)
