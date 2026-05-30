"""
Archivo: tests.py
Descripcion: Define pruebas automatizadas para los flujos principales de autenticacion, carrito, checkout y cancelacion.
Dependencias: Django test, Django auth, Django urls, Django REST Framework y modelos de store
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .models import Customer, Order, OrderItem, Product


class StoreApiTests(APITestCase):
    """
    Nombre: StoreApiTests
    Descripcion: Agrupa pruebas de API para los riesgos principales del ecommerce.
    """

    def setUp(self):
        """
        Nombre: setUp
        Descripcion: Crea datos base reutilizables para las pruebas.
        """
        self.product = Product.objects.create(
            name="Producto prueba",
            description="Descripcion de prueba",
            price=Decimal("10.00"),
            stock=5,
        )

    def set_session_cart(self, cart):
        """
        Nombre: set_session_cart
        Descripcion: Guarda un carrito en la sesion del cliente de pruebas.
        """
        session = self.client.session
        session["cart"] = cart
        session.save()

    def create_user(self):
        """
        Nombre: create_user
        Descripcion: Crea un usuario valido para pruebas autenticadas.
        Retorna: Usuario creado.
        """
        return User.objects.create_user(
            username="cliente",
            email="cliente@example.com",
            password="ClaveSegura123",
        )

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(
            username="existente",
            email="cliente@example.com",
            password="ClaveSegura123",
        )

        response = self.client.post(
            reverse("auth_register"),
            {
                "username": "nuevo",
                "email": "cliente@example.com",
                "password": "ClaveSegura123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_rejects_email_associated_to_customer(self):
        Customer.objects.create(
            first_name="Cliente",
            last_name="Existente",
            email="cliente@example.com",
        )

        response = self.client.post(
            reverse("auth_register"),
            {
                "username": "nuevo",
                "email": "cliente@example.com",
                "password": "ClaveSegura123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_login_accepts_username(self):
        self.create_user()

        response = self.client.post(
            reverse("auth_login"),
            {
                "email": "cliente",
                "password": "ClaveSegura123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "cliente")

    def test_cart_add_rejects_invalid_quantity_and_stock_excess(self):
        response = self.client.post(
            reverse("api_cart_add"),
            {
                "productId": self.product.id,
                "quantity": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            reverse("api_cart_add"),
            {
                "productId": self.product.id,
                "quantity": 6,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cart_add_accepts_valid_quantity(self):
        response = self.client.post(
            reverse("api_cart_add"),
            {
                "productId": self.product.id,
                "quantity": 2,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["cart"][str(self.product.id)], 2)

    def test_checkout_creates_order_and_discounts_stock(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 2})

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingName": "Cliente Prueba",
                "shippingPhone": "3000000000",
                "shippingAddress": "Calle 1",
                "shippingCity": "Medellin",
                "shippingNotes": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

        order = Order.objects.get(id=response.data["order_id"])
        self.assertEqual(order.status, "pagado")
        self.assertEqual(order.shipping_city, "Medellin")
        self.assertEqual(self.client.session.get("cart"), {})

    def test_cancel_order_restores_stock_once(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        self.product.stock = 3
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            customer=customer,
            status="pagado",
            completed=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
        )

        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.post(reverse("cancel_order", args=[order.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(order.status, "cancelado")

        response = self.client.post(reverse("cancel_order", args=[order.id]))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    def test_cancel_delivered_order_is_rejected(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        order = Order.objects.create(
            customer=customer,
            status="entregado",
            completed=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
        )

        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.post(reverse("cancel_order", args=[order.id]))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(order.status, "entregado")

    def test_cancel_pending_order_does_not_restore_stock(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        order = Order.objects.create(
            customer=customer,
            status="pendiente",
            completed=False,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
        )

        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.post(reverse("cancel_order", args=[order.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(order.status, "cancelado")
