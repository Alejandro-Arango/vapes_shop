"""
Archivo: urls.py
Descripcion: Define las rutas principales de la aplicacion store para vistas, productos, carrito, ordenes y autenticacion.
Dependencias: Django path y vistas de la aplicacion store
"""

from django.urls import path

from . import (
    views,
    views_api,
    views_auth,
    views_cart,
    views_contact,
    views_orders,
)


urlpatterns = [
    # Vista principal
    path("", views.home, name="home"),

    # Salud del servicio
    path("api/health/", views_api.health_check, name="health_check"),

    # Productos
    path("api/categories/", views_api.api_categories, name="api_categories"),
    path("api/products/", views_api.api_products, name="api_products"),

    # Contacto
    path("api/contact/", views_contact.contact, name="contact"),

    # Carrito
    path("api/cart/", views_cart.api_cart, name="api_cart"),
    path("api/cart/add/", views_cart.api_cart_add, name="api_cart_add"),
    path("api/cart/remove/", views_cart.api_cart_remove, name="api_cart_remove"),
    path("api/cart/decrease/", views_cart.api_cart_decrease, name="api_cart_decrease"),
    path("api/cart/clear/", views_cart.api_cart_clear, name="api_cart_clear"),
    # Ordenes
    path("api/orders/checkout/", views_orders.checkout, name="checkout"),
    path("api/orders/my/", views_orders.my_orders, name="my_orders"),
    path("api/orders/<int:order_id>/", views_orders.order_detail, name="order_detail"),
    path("api/orders/cancel/<int:order_id>/", views_orders.cancel_order, name="cancel_order"),

    # Autenticacion
    path("api/auth/register/", views_auth.register, name="auth_register"),
    path("api/auth/login/", views_auth.login_view, name="auth_login"),
    path("api/auth/logout/", views_auth.logout_view, name="auth_logout"),
    path("api/auth/me/", views_auth.me, name="auth_me"),
]
