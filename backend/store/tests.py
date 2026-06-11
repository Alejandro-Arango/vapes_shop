"""
Archivo: tests.py
Descripcion: Define pruebas automatizadas para los flujos principales de autenticacion, carrito, checkout y cancelacion.
Dependencias: Django test, Django auth, Django urls, Django REST Framework y modelos de store
"""

import os
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, override_settings
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from mi_tienda.settings import (
    LOG_LEVEL_CHOICES,
    env_bool,
    env_choice,
    env_digits,
)

from .admin import ContactLeadAdmin, EventLogAdmin, OrderAdmin, build_csv_response
from .audit import log_event
from .models import ContactLead, Customer, EventLog, Order, OrderItem, Product
from .throttles import (
    AuthAnonRateThrottle,
    CartRateThrottle,
    CheckoutUserRateThrottle,
    ContactAnonRateThrottle,
)
from .views_orders import build_cart_audit_metadata


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
        self.admin_site = AdminSite()
        self.request_factory = RequestFactory()

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

    def create_admin_request(self):
        """
        Nombre: create_admin_request
        Descripcion: Construye un request autenticado para probar acciones del admin.
        Retorna: Request con usuario administrador.
        """
        request = self.request_factory.get("/admin/")
        next_id = User.objects.count() + 1
        request.user = User.objects.create_superuser(
            username=f"admin{next_id}",
            email=f"admin{next_id}@example.com",
            password="ClaveSegura123",
        )

        return request

    def test_home_sets_security_headers(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
        self.assertEqual(response.headers["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(
            response.headers["Permissions-Policy"],
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )

    def test_health_check_reports_available_service(self):
        response = self.client.get(reverse("health_check"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["database"], "available")
        self.assertEqual(response.headers["Cache-Control"], "no-store, max-age=0")
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["Expires"], "0")

    def test_sensitive_api_responses_are_not_cached(self):
        response = self.client.get(reverse("api_cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.headers["Cache-Control"], "no-store, max-age=0")
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["Expires"], "0")

    def test_public_product_api_keeps_default_cache_headers(self):
        response = self.client.get(reverse("api_products"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("no-store", response.headers.get("Cache-Control", ""))

    def test_product_constraints_reject_negative_values(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    name="Precio invalido",
                    description="Producto invalido",
                    price=Decimal("-1.00"),
                    stock=1,
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    name="Stock invalido",
                    description="Producto invalido",
                    price=Decimal("1.00"),
                    stock=-1,
                )

    def test_order_item_constraints_reject_invalid_quantity_and_price(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        order = Order.objects.create(customer=customer)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrderItem.objects.create(
                    order=order,
                    product=self.product,
                    quantity=0,
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrderItem.objects.create(
                    order=order,
                    product=self.product,
                    quantity=1,
                    unit_price=Decimal("-1.00"),
                )

    def test_status_constraints_reject_invalid_values(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ContactLead.objects.create(
                    email="contacto@example.com",
                    status="estado_invalido",
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EventLog.objects.create(
                    event_type="test_event",
                    severity="critico",
                    user=user,
                    message="Evento con severidad invalida.",
                )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(
                    customer=customer,
                    status="estado_invalido",
                )

    def test_request_limits_are_configured(self):
        self.assertIsInstance(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, int)
        self.assertIsInstance(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, int)
        self.assertIsInstance(settings.DATA_UPLOAD_MAX_NUMBER_FIELDS, int)
        self.assertIsInstance(settings.DATA_UPLOAD_MAX_NUMBER_FILES, int)
        self.assertIsInstance(settings.SESSION_COOKIE_AGE, int)
        self.assertIsInstance(settings.EMAIL_TIMEOUT, int)
        self.assertGreater(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 0)
        self.assertGreater(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 0)
        self.assertGreater(settings.DATA_UPLOAD_MAX_NUMBER_FIELDS, 0)
        self.assertGreater(settings.DATA_UPLOAD_MAX_NUMBER_FILES, 0)
        self.assertGreaterEqual(settings.SESSION_COOKIE_AGE, 300)
        self.assertGreaterEqual(settings.EMAIL_TIMEOUT, 1)

    def test_hsts_seconds_is_configured_as_non_negative_integer(self):
        self.assertIsInstance(settings.SECURE_HSTS_SECONDS, int)
        self.assertGreaterEqual(settings.SECURE_HSTS_SECONDS, 0)

    def test_env_bool_rejects_invalid_values(self):
        with patch.dict(os.environ, {"TEST_BOOL": "tru"}):
            with self.assertRaises(ImproperlyConfigured):
                env_bool("TEST_BOOL")

        with patch.dict(os.environ, {"TEST_BOOL": "yes"}):
            self.assertTrue(env_bool("TEST_BOOL"))

        with patch.dict(os.environ, {"TEST_BOOL": "off"}):
            self.assertFalse(env_bool("TEST_BOOL"))

    def test_env_choice_validates_log_levels(self):
        with patch.dict(os.environ, {"TEST_LOG_LEVEL": "warning"}):
            self.assertEqual(
                env_choice("TEST_LOG_LEVEL", "ERROR", LOG_LEVEL_CHOICES),
                "WARNING",
            )

        with patch.dict(os.environ, {"TEST_LOG_LEVEL": "WARNNIG"}):
            with self.assertRaises(ImproperlyConfigured):
                env_choice("TEST_LOG_LEVEL", "ERROR", LOG_LEVEL_CHOICES)

    def test_env_digits_normalizes_whatsapp_number(self):
        with patch.dict(os.environ, {"TEST_PHONE": "+57 301-660-4375"}):
            self.assertEqual(
                env_digits("TEST_PHONE", "", min_digits=7, max_digits=15),
                "573016604375",
            )

        with patch.dict(os.environ, {"TEST_PHONE": "abc"}):
            with self.assertRaises(ImproperlyConfigured):
                env_digits("TEST_PHONE", "", min_digits=7, max_digits=15)

    def test_cart_audit_metadata_summarizes_payload(self):
        metadata = build_cart_audit_metadata(
            {
                "2": 1,
                "invalid": "dato-controlado-por-sesion",
                "1": 3,
            }
        )

        self.assertEqual(metadata["cart_items"], 3)
        self.assertEqual(metadata["invalid_items"], 1)
        self.assertEqual(metadata["product_ids"], [1, 2])
        self.assertFalse(metadata["product_ids_truncated"])
        self.assertNotIn("cart", metadata)
        self.assertNotIn("dato-controlado-por-sesion", str(metadata))

    def test_register_creates_event_without_personal_metadata(self):
        response = self.client.post(
            reverse("auth_register"),
            {
                "username": "nuevo",
                "email": "nuevo@example.com",
                "password": "ClaveSegura123",
            },
            format="json",
        )

        event = EventLog.objects.get(event_type="auth_register_success")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(event.metadata["user_id"], response.data["id"])
        self.assertNotIn("email", event.metadata)
        self.assertNotIn("username", event.metadata)

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

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user(
            username="cliente",
            email="existente@example.com",
            password="ClaveSegura123",
        )

        response = self.client.post(
            reverse("auth_register"),
            {
                "username": "CLIENTE",
                "email": "nuevo@example.com",
                "password": "ClaveSegura123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            reverse("auth_register"),
            {
                "username": "nuevo",
                "email": "nuevo@example.com",
                "password": "123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

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
        self.assertTrue(
            EventLog.objects.filter(event_type="auth_login_success").exists()
        )

    def test_login_links_existing_customer_by_email(self):
        user = self.create_user()
        customer = Customer.objects.create(
            first_name="Cliente",
            last_name="Preexistente",
            email=user.email,
        )

        response = self.client.post(
            reverse("auth_login"),
            {
                "email": user.email,
                "password": "ClaveSegura123",
            },
            format="json",
        )

        customer.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(customer.user, user)

    def test_failed_login_creates_event_log(self):
        response = self.client.post(
            reverse("auth_login"),
            {
                "email": "no-existe",
                "password": "ClaveIncorrecta123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        event = EventLog.objects.get(event_type="auth_login_failed")

        self.assertEqual(event.metadata["identifier_type"], "username")
        self.assertNotIn("identifier", event.metadata)
        self.assertNotIn("no-existe", str(event.metadata))

    def test_login_is_rate_limited(self):
        cache.clear()
        login_data = {
            "email": "no-existe",
            "password": "ClaveIncorrecta123",
        }

        try:
            with patch.object(AuthAnonRateThrottle, "rate", "2/min", create=True):
                for _ in range(2):
                    response = self.client.post(
                        reverse("auth_login"),
                        login_data,
                        format="json",
                    )

                    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

                response = self.client.post(
                    reverse("auth_login"),
                    login_data,
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        finally:
            cache.clear()

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        CONTACT_NOTIFICATION_EMAIL="admin@example.com",
        DEFAULT_FROM_EMAIL="no-reply@example.com",
    )
    def test_contact_form_saves_lead_sends_email_and_returns_whatsapp(self):
        response = self.client.post(
            reverse("contact"),
            {
                "name": " Visitante ",
                "email": " VISITANTE@Example.COM ",
                "phone": " 300 000 0000 ",
                "message": " Quiero saber si hay sabores disponibles. ",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        lead = ContactLead.objects.get()

        self.assertEqual(lead.email, "visitante@example.com")
        self.assertEqual(lead.name, "Visitante")
        self.assertEqual(lead.phone, "300 000 0000")
        self.assertEqual(lead.message, "Quiero saber si hay sabores disponibles.")
        self.assertEqual(lead.status, "nuevo")
        self.assertTrue(lead.email_notification_sent)
        self.assertIn("wa.me", response.data["whatsapp_url"])
        self.assertIn("visitante%40example.com", response.data["whatsapp_url"])
        self.assertEqual(len(mail.outbox), 1)
        event = EventLog.objects.get(
            event_type="contact_received",
            metadata__lead_id=lead.id,
        )

        self.assertEqual(event.metadata["status"], "nuevo")
        self.assertNotIn("email", event.metadata)
        self.assertNotIn("phone", event.metadata)

    def test_contact_form_rejects_invalid_phone(self):
        response = self.client.post(
            reverse("contact"),
            {
                "email": "visitante@example.com",
                "phone": "abc",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)
        self.assertTrue(
            EventLog.objects.filter(event_type="contact_invalid").exists()
        )

    def test_contact_form_is_rate_limited(self):
        cache.clear()
        contact_data = {
            "email": "visitante@example.com",
            "phone": "abc",
        }

        try:
            with patch.object(ContactAnonRateThrottle, "rate", "1/min", create=True):
                response = self.client.post(
                    reverse("contact"),
                    contact_data,
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

                response = self.client.post(
                    reverse("contact"),
                    contact_data,
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        finally:
            cache.clear()

    def test_contact_form_rejects_oversized_phone_and_message(self):
        response = self.client.post(
            reverse("contact"),
            {
                "email": "visitante@example.com",
                "phone": "1234567890123456",
                "message": "Necesito informacion.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

        response = self.client.post(
            reverse("contact"),
            {
                "email": "visitante@example.com",
                "phone": "3000000000",
                "message": "x" * 1001,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message", response.data)

    def test_order_endpoints_require_authentication(self):
        responses = [
            self.client.post(reverse("checkout"), {}, format="json"),
            self.client.get(reverse("my_orders")),
            self.client.get(reverse("order_detail", args=[1])),
            self.client.post(reverse("cancel_order", args=[1])),
        ]

        for response in responses:
            self.assertIn(
                response.status_code,
                (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
            )

    def test_checkout_is_rate_limited_for_authenticated_user(self):
        cache.clear()
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")

        try:
            with patch.object(CheckoutUserRateThrottle, "rate", "1/min", create=True):
                response = self.client.post(reverse("checkout"), {}, format="json")

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

                response = self.client.post(reverse("checkout"), {}, format="json")

                self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        finally:
            cache.clear()

    def test_products_api_returns_only_active_products(self):
        newest_product = Product.objects.create(
            name="Producto nuevo",
            description="Debe aparecer primero en catalogo.",
            price=Decimal("18.00"),
            stock=3,
        )
        inactive_product = Product.objects.create(
            name="Producto oculto",
            description="No debe aparecer en catalogo.",
            price=Decimal("15.00"),
            stock=4,
            is_active=False,
        )

        response = self.client.get(reverse("api_products"))
        product_ids = [product["id"] for product in response.data]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.product.id, product_ids)
        self.assertEqual(product_ids[0], newest_product.id)
        self.assertNotIn(inactive_product.id, product_ids)
        self.assertNotIn("is_active", response.data[0])

    def test_cart_add_rejects_invalid_quantity_and_stock_excess(self):
        invalid_quantities = (0, "1.5", True, "abc")

        for invalid_quantity in invalid_quantities:
            response = self.client.post(
                reverse("api_cart_add"),
                {
                    "productId": self.product.id,
                    "quantity": invalid_quantity,
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

    def test_cart_add_is_rate_limited(self):
        cache.clear()
        cart_data = {
            "productId": self.product.id,
            "quantity": 0,
        }

        try:
            with patch.object(CartRateThrottle, "rate", "1/min", create=True):
                response = self.client.post(
                    reverse("api_cart_add"),
                    cart_data,
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

                response = self.client.post(
                    reverse("api_cart_add"),
                    cart_data,
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        finally:
            cache.clear()

    def test_cart_rejects_inactive_product_and_cleans_existing_item(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("api_cart_add"),
            {
                "productId": self.product.id,
                "quantity": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.set_session_cart({str(self.product.id): 1})
        response = self.client.get(reverse("api_cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(self.client.session.get("cart"), {})

    def test_cart_syncs_existing_items_with_current_stock(self):
        self.set_session_cart({str(self.product.id): 4})
        self.product.stock = 2
        self.product.save(update_fields=["stock"])

        response = self.client.get(reverse("api_cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"][0]["quantity"], 2)
        self.assertEqual(self.client.session.get("cart")[str(self.product.id)], 2)

        self.product.stock = 0
        self.product.save(update_fields=["stock"])

        response = self.client.get(reverse("api_cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(self.client.session.get("cart"), {})

    def test_checkout_syncs_cart_before_payment_when_stock_changes(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 4})
        self.product.stock = 2
        self.product.save(update_fields=["stock"])

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingName": "Cliente Prueba",
                "shippingPhone": "3000000000",
                "shippingAddress": "Calle 1",
                "shippingCity": "Medellin",
                "shippingNotes": "",
                "ageConfirmed": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["cart_updated"])
        self.assertEqual(self.client.session.get("cart")[str(self.product.id)], 2)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)

    def test_checkout_rejects_inactive_product(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 1})
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingName": "Cliente Prueba",
                "shippingPhone": "3000000000",
                "shippingAddress": "Calle 1",
                "shippingCity": "Medellin",
                "shippingNotes": "",
                "ageConfirmed": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(Order.objects.count(), 0)
        self.assertTrue(
            EventLog.objects.filter(event_type="checkout_failed").exists()
        )

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
                "ageConfirmed": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

        order = Order.objects.get(id=response.data["order_id"])
        self.assertEqual(order.status, "pagado")
        self.assertEqual(order.shipping_city, "Medellin")
        self.assertTrue(order.age_verified)
        self.assertEqual(self.client.session.get("cart"), {})
        item = order.orderitem_set.get()
        self.assertEqual(item.product_name, "Producto prueba")
        self.assertEqual(item.unit_price, Decimal("10.00"))
        self.assertTrue(
            EventLog.objects.filter(
                event_type="checkout_success",
                metadata__order_id=order.id,
            ).exists()
        )

        self.product.name = "Producto renombrado"
        self.product.price = Decimal("99.00")
        self.product.save(update_fields=["name", "price"])

        orders_response = self.client.get(reverse("my_orders"))

        self.assertEqual(orders_response.status_code, status.HTTP_200_OK)
        self.assertEqual(orders_response.data["orders"][0]["status"], "pagado")
        self.assertEqual(orders_response.data["orders"][0]["status_label"], "Pagado")
        self.assertEqual(orders_response.data["orders"][0]["total"], 20.0)
        self.assertEqual(
            orders_response.data["orders"][0]["items"][0]["product"]["name"],
            "Producto prueba",
        )
        self.assertEqual(
            orders_response.data["orders"][0]["items"][0]["product"]["price"],
            10.0,
        )
        self.assertNotIn(
            "stock",
            orders_response.data["orders"][0]["items"][0]["product"],
        )
        self.assertEqual(
            orders_response.data["orders"][0]["items"][0]["line_total"],
            20.0,
        )

        with self.assertRaises(ProtectedError):
            self.product.delete()

    def test_checkout_links_existing_customer_by_email(self):
        user = self.create_user()
        customer = Customer.objects.create(
            first_name="Cliente",
            last_name="Preexistente",
            email=user.email,
        )
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 1})

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingName": "Cliente Prueba",
                "shippingPhone": "3000000000",
                "shippingAddress": "Calle 1",
                "shippingCity": "Medellin",
                "shippingNotes": "",
                "ageConfirmed": True,
            },
            format="json",
        )

        customer.refresh_from_db()
        order = Order.objects.get(id=response.data["order_id"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(customer.user, user)
        self.assertEqual(order.customer, customer)

    def test_user_cannot_access_or_cancel_other_user_order(self):
        owner = self.create_user()
        intruder = User.objects.create_user(
            username="intruso",
            email="intruso@example.com",
            password="ClaveSegura123",
        )
        owner_customer = Customer.objects.create(
            user=owner,
            first_name="Cliente",
            last_name="Propietario",
            email=owner.email,
        )
        Customer.objects.create(
            user=intruder,
            first_name="Cliente",
            last_name="Intruso",
            email=intruder.email,
        )
        order = Order.objects.create(
            customer=owner_customer,
            status="pagado",
            completed=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
        )

        self.client.login(username=intruder.username, password="ClaveSegura123")

        orders_response = self.client.get(reverse("my_orders"))
        detail_response = self.client.get(reverse("order_detail", args=[order.id]))
        cancel_response = self.client.post(reverse("cancel_order", args=[order.id]))

        self.assertEqual(orders_response.status_code, status.HTTP_200_OK)
        self.assertEqual(orders_response.data["orders"], [])
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(cancel_response.status_code, status.HTTP_404_NOT_FOUND)

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, "pagado")
        self.assertEqual(self.product.stock, 5)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_detail_failed",
                metadata__order_id=order.id,
            ).exists()
        )
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_cancel_failed",
                metadata__order_id=order.id,
            ).exists()
        )

    def test_checkout_rejects_missing_age_confirmation(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 1})

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

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(Order.objects.count(), 0)
        self.assertTrue(
            EventLog.objects.filter(event_type="checkout_failed").exists()
        )

    def test_checkout_rejects_invalid_shipping_phone(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 1})

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingName": "Cliente Prueba",
                "shippingPhone": "telefono-invalido",
                "shippingAddress": "Calle 1",
                "shippingCity": "Medellin",
                "shippingNotes": "",
                "ageConfirmed": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("telefono", response.data["error"].lower())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(Order.objects.count(), 0)

    def test_checkout_rejects_oversized_shipping_data(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 1})

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingName": "Cliente Prueba",
                "shippingPhone": "3000000000",
                "shippingAddress": "Calle 1",
                "shippingCity": "Medellin",
                "shippingNotes": "x" * 501,
                "ageConfirmed": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("notas", response.data["error"].lower())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(Order.objects.count(), 0)

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
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_cancel_success",
                metadata__order_id=order.id,
            ).exists()
        )

        response = self.client.post(reverse("cancel_order", args=[order.id]))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertTrue(
            EventLog.objects.filter(event_type="order_cancel_failed").exists()
        )

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

    def test_cancel_preparing_order_is_rejected(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        order = Order.objects.create(
            customer=customer,
            status="en_preparacion",
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
        order.refresh_from_db()
        self.assertEqual(order.status, "en_preparacion")

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

    def test_admin_exports_contacts_to_csv(self):
        ContactLead.objects.create(
            name="Visitante",
            email="visitante@example.com",
            phone="3000000000",
            message="Necesito informacion.",
        )
        admin_model = ContactLeadAdmin(ContactLead, self.admin_site)

        response = admin_model.export_contacts_csv(
            self.create_admin_request(),
            ContactLead.objects.all(),
        )

        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("contactos.csv", response["Content-Disposition"])
        self.assertIn("visitante@example.com", content)
        self.assertIn("Necesito informacion.", content)

    def test_admin_csv_export_escapes_formula_values(self):
        response = build_csv_response(
            "seguro.csv",
            ("Valor", "Normal"),
            (
                ("=IMPORTXML(\"http://example.com\")", "texto"),
                ("+SUM(1,1)", "-10"),
                ("@usuario", 100),
                ("  =SUM(2,2)", "normal"),
            ),
        )

        content = response.content.decode()

        self.assertIn("'=IMPORTXML", content)
        self.assertIn("'+SUM(1,1)", content)
        self.assertIn("'-10", content)
        self.assertIn("'@usuario", content)
        self.assertIn("'  =SUM(2,2)", content)

    def test_admin_exports_orders_to_csv(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        order = Order.objects.create(
            customer=customer,
            status="pagado",
            completed=True,
            age_verified=True,
            shipping_name="Cliente Prueba",
            shipping_phone="3000000000",
            shipping_city="Medellin",
            shipping_address="Calle 1",
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
        )
        self.product.price = Decimal("99.00")
        self.product.save(update_fields=["price"])
        admin_model = OrderAdmin(Order, self.admin_site)

        response = admin_model.export_orders_csv(
            self.create_admin_request(),
            Order.objects.all(),
        )

        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("ordenes.csv", response["Content-Disposition"])
        self.assertIn("cliente@example.com", content)
        self.assertIn("Medellin", content)
        self.assertIn("20.00", content)

    def test_admin_can_mark_orders_as_preparing_and_refunded(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        order = Order.objects.create(
            customer=customer,
            status="pagado",
            completed=True,
        )
        admin_model = OrderAdmin(Order, self.admin_site)
        admin_model.message_user = lambda *args, **kwargs: None

        admin_model.mark_as_preparing(
            self.create_admin_request(),
            Order.objects.filter(id=order.id),
        )

        order.refresh_from_db()
        self.assertEqual(order.status, "en_preparacion")
        self.assertTrue(order.completed)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="admin_order_preparing",
                metadata__order_id=order.id,
            ).exists()
        )

        admin_model.mark_as_refunded(
            self.create_admin_request(),
            Order.objects.filter(id=order.id),
        )

        order.refresh_from_db()
        self.assertEqual(order.status, "reembolsado")
        self.assertFalse(order.completed)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="admin_order_refunded",
                metadata__order_id=order.id,
            ).exists()
        )

    def test_log_event_redacts_sensitive_metadata(self):
        event = log_event(
            "security_test",
            "Evento de prueba con metadata sensible.",
            metadata={
                "password": "ClaveSegura123",
                "safe": "visible",
                "nested": {
                    "access_token": "token-secreto",
                },
                "items": [
                    {
                        "secret": "valor-secreto",
                        "public": "ok",
                    },
                ],
            },
        )

        self.assertEqual(event.metadata["password"], "[redacted]")
        self.assertEqual(event.metadata["safe"], "visible")
        self.assertEqual(event.metadata["nested"]["access_token"], "[redacted]")
        self.assertEqual(event.metadata["items"][0]["secret"], "[redacted]")
        self.assertEqual(event.metadata["items"][0]["public"], "ok")

    def test_admin_exports_events_to_csv(self):
        user = self.create_user()
        EventLog.objects.create(
            event_type="checkout_success",
            severity="info",
            user=user,
            message="Compra realizada correctamente.",
            path="/api/orders/checkout/",
            metadata={"order_id": 1},
        )
        admin_model = EventLogAdmin(EventLog, self.admin_site)

        response = admin_model.export_events_csv(
            self.create_admin_request(),
            EventLog.objects.all(),
        )

        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("eventos.csv", response["Content-Disposition"])
        self.assertIn("checkout_success", content)
        self.assertIn("Compra realizada correctamente.", content)
