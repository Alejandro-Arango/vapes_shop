"""
Archivo: tests.py
Descripcion: Define pruebas automatizadas para los flujos principales de autenticacion, carrito, checkout y cancelacion.
Dependencias: Django test, Django auth, Django urls, Django REST Framework y modelos de store
"""

import os
from datetime import timedelta
from io import StringIO
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from mi_tienda.settings import (
    CROSS_ORIGIN_OPENER_POLICY_CHOICES,
    LOG_LEVEL_CHOICES,
    REFERRER_POLICY_CHOICES,
    env_admin_url_path,
    env_bool,
    env_choice,
    env_digits,
    env_ip_list,
    env_lower_choice,
    env_port,
    env_throttle_rate,
)

from .admin import ContactLeadAdmin, EventLogAdmin, OrderAdmin, build_csv_response
from .admin_dashboard import build_business_dashboard_context
from .audit import get_client_ip, log_event
from .models import (
    Category,
    ContactLead,
    Customer,
    DiscountCode,
    EventLog,
    FavoriteProduct,
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    ProductReview,
    ShippingAddress,
)
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

    @override_settings(ADMIN_ALLOWED_IPS=("127.0.0.1",), ADMIN_URL_PATH="admin/")
    def test_admin_access_rejects_disallowed_ip(self):
        response = self.client.get("/admin/", REMOTE_ADDR="203.0.113.10")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(ADMIN_ALLOWED_IPS=("127.0.0.1",), ADMIN_URL_PATH="admin/")
    def test_admin_access_allows_configured_ip(self):
        response = self.client.get("/admin/", REMOTE_ADDR="127.0.0.1")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

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
        self.assertIsInstance(settings.EMAIL_PORT, int)
        self.assertIn(
            settings.CACHES["default"]["BACKEND"],
            (
                "django.core.cache.backends.locmem.LocMemCache",
                "django.core.cache.backends.db.DatabaseCache",
            ),
        )
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

    def test_env_lower_choice_validates_security_headers(self):
        with patch.dict(os.environ, {"TEST_REFERRER": "SAME-ORIGIN"}):
            self.assertEqual(
                env_lower_choice(
                    "TEST_REFERRER",
                    "no-referrer",
                    REFERRER_POLICY_CHOICES,
                ),
                "same-origin",
            )

        with patch.dict(os.environ, {"TEST_COOP": "invalid-policy"}):
            with self.assertRaises(ImproperlyConfigured):
                env_lower_choice(
                    "TEST_COOP",
                    "same-origin",
                    CROSS_ORIGIN_OPENER_POLICY_CHOICES,
                )

    def test_env_digits_normalizes_whatsapp_number(self):
        with patch.dict(os.environ, {"TEST_PHONE": "+57 301-660-4375"}):
            self.assertEqual(
                env_digits("TEST_PHONE", "", min_digits=7, max_digits=15),
                "573016604375",
            )

        with patch.dict(os.environ, {"TEST_PHONE": "abc"}):
            with self.assertRaises(ImproperlyConfigured):
                env_digits("TEST_PHONE", "", min_digits=7, max_digits=15)

    def test_env_throttle_rate_validates_format(self):
        with patch.dict(os.environ, {"TEST_THROTTLE": "20/MIN"}):
            self.assertEqual(
                env_throttle_rate("TEST_THROTTLE", "10/hour"),
                "20/min",
            )

        invalid_rates = ("0/min", "20", "abc/min", "20/week")

        for invalid_rate in invalid_rates:
            with patch.dict(os.environ, {"TEST_THROTTLE": invalid_rate}):
                with self.assertRaises(ImproperlyConfigured):
                    env_throttle_rate("TEST_THROTTLE", "10/hour")

    def test_env_port_validates_tcp_port(self):
        with patch.dict(os.environ, {"TEST_PORT": "3306"}):
            self.assertEqual(env_port("TEST_PORT", "5432"), "3306")

        invalid_ports = ("0", "65536", "abc")

        for invalid_port in invalid_ports:
            with patch.dict(os.environ, {"TEST_PORT": invalid_port}):
                with self.assertRaises(ImproperlyConfigured):
                    env_port("TEST_PORT", "5432")

    def test_env_ip_list_rejects_invalid_values(self):
        with patch.dict(os.environ, {"TEST_ALLOWED_IPS": "127.0.0.1,192.0.2.10"}):
            self.assertEqual(
                env_ip_list("TEST_ALLOWED_IPS"),
                ["127.0.0.1", "192.0.2.10"],
            )

        with patch.dict(os.environ, {"TEST_ALLOWED_IPS": "127.0.0.1,ip-invalida"}):
            with self.assertRaises(ImproperlyConfigured):
                env_ip_list("TEST_ALLOWED_IPS")

    def test_env_admin_url_path_normalizes_path(self):
        with patch.dict(os.environ, {"TEST_ADMIN_PATH": "/panel-seguro/"}):
            self.assertEqual(
                env_admin_url_path("TEST_ADMIN_PATH", "admin"),
                "panel-seguro/",
            )

        with patch.dict(os.environ, {"TEST_ADMIN_PATH": "/"}):
            with self.assertRaises(ImproperlyConfigured):
                env_admin_url_path("TEST_ADMIN_PATH", "admin")

    def test_production_check_rejects_insecure_configuration(self):
        with self.assertRaises(CommandError):
            call_command(
                "production_check",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    @override_settings(
        DEBUG=False,
        SECRET_KEY="prod-ready-value-with-more-than-fifty-characters-1234567890",
        ALLOWED_HOSTS=["example.com", "www.example.com"],
        CSRF_TRUSTED_ORIGINS=["https://example.com", "https://www.example.com"],
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=True,
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        SECURE_HSTS_PRELOAD=True,
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.mysql",
                "NAME": "vapes_shop",
                "USER": "vapes_user",
                "PASSWORD": "valor-seguro-db-123",
                "HOST": "127.0.0.1",
                "PORT": "3306",
            }
        },
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                "LOCATION": "django_cache",
            }
        },
        ADMIN_URL_PATH="panel-seguro/",
        ADMIN_ALLOWED_IPS=("127.0.0.1",),
        TRUST_X_FORWARDED_FOR=True,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST="smtp.example.com",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        DEFAULT_FROM_EMAIL="Vape Shop <no-reply@example.com>",
        CONTACT_NOTIFICATION_EMAIL="admin@example.com",
        ORDER_NOTIFICATION_EMAIL="orders@example.com",
        CONTACT_WHATSAPP_NUMBER="573016604375",
    )
    def test_production_check_accepts_hardened_configuration(self):
        output = StringIO()

        call_command("production_check", stdout=output)

        self.assertIn("Configuracion de produccion validada", output.getvalue())

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
        self.assertEqual(response.data["customer"]["email"], "nuevo@example.com")
        self.assertEqual(response.data["default_shipping"]["name"], "nuevo")
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
        self.assertEqual(response.data["customer"]["first_name"], "Cliente")
        self.assertEqual(response.data["default_shipping"]["name"], "Cliente Preexistente")

    def test_me_returns_default_shipping_from_latest_order(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Perfil",
            email=user.email,
            phone="3001112222",
        )
        Order.objects.create(
            customer=customer,
            shipping_name="Cliente Antiguo",
            shipping_phone="3000000000",
            shipping_address="Calle Antigua",
            shipping_city="Envigado",
            shipping_notes="Entrega antigua",
        )
        latest_order = Order.objects.create(
            customer=customer,
            shipping_name="Cliente Actual",
            shipping_phone="3009998888",
            shipping_address="Calle Nueva",
            shipping_city="Medellin",
            shipping_notes="Porteria principal",
        )

        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.get(reverse("auth_me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["customer"]["phone"], "3001112222")
        self.assertEqual(response.data["default_shipping"]["name"], latest_order.shipping_name)
        self.assertEqual(response.data["default_shipping"]["phone"], "3009998888")
        self.assertEqual(response.data["default_shipping"]["address"], "Calle Nueva")
        self.assertEqual(response.data["default_shipping"]["city"], "Medellin")
        self.assertEqual(response.data["default_shipping"]["notes"], "Porteria principal")

    def test_profile_update_requires_auth_and_updates_customer(self):
        unauthenticated_response = self.client.post(
            reverse("auth_profile"),
            {
                "first_name": "Cliente",
                "last_name": "Perfil",
                "phone": "3001234567",
            },
            format="json",
        )

        self.assertIn(
            unauthenticated_response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")

        invalid_response = self.client.post(
            reverse("auth_profile"),
            {
                "first_name": "Cliente",
                "last_name": "Perfil",
                "phone": "telefono",
            },
            format="json",
        )

        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", invalid_response.data)

        response = self.client.post(
            reverse("auth_profile"),
            {
                "first_name": "Cliente",
                "last_name": "Actualizado",
                "phone": "300 123 4567",
            },
            format="json",
        )

        customer = user.customer
        customer.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(customer.first_name, "Cliente")
        self.assertEqual(customer.last_name, "Actualizado")
        self.assertEqual(customer.phone, "300 123 4567")
        self.assertEqual(response.data["customer"]["phone"], "300 123 4567")
        self.assertEqual(response.data["default_shipping"]["phone"], "300 123 4567")
        self.assertTrue(
            EventLog.objects.filter(event_type="profile_update_success").exists()
        )

    def test_shipping_addresses_crud_and_default_shipping(self):
        unauthenticated_response = self.client.get(reverse("shipping_addresses"))

        self.assertIn(
            unauthenticated_response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")

        invalid_response = self.client.post(
            reverse("shipping_addresses"),
            {
                "label": "Casa",
                "name": "Cliente Prueba",
                "phone": "telefono",
                "address": "Calle 1",
                "city": "Medellin",
            },
            format="json",
        )

        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", invalid_response.data)

        first_response = self.client.post(
            reverse("shipping_addresses"),
            {
                "label": "Casa",
                "name": "Cliente Prueba",
                "phone": "3001234567",
                "address": "Calle 1",
                "city": "Medellin",
                "notes": "Porteria",
            },
            format="json",
        )
        first_address = ShippingAddress.objects.get(label="Casa")

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(first_address.is_default)
        self.assertEqual(first_response.data["default_shipping"]["id"], first_address.id)

        second_response = self.client.post(
            reverse("shipping_addresses"),
            {
                "label": "Trabajo",
                "name": "Cliente Oficina",
                "phone": "3007654321",
                "address": "Carrera 2",
                "city": "Envigado",
            },
            format="json",
        )
        second_address = ShippingAddress.objects.get(label="Trabajo")

        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(second_address.is_default)

        default_response = self.client.patch(
            reverse("shipping_address_detail", args=[second_address.id]),
            {"is_default": True},
            format="json",
        )
        first_address.refresh_from_db()
        second_address.refresh_from_db()

        self.assertEqual(default_response.status_code, status.HTTP_200_OK)
        self.assertFalse(first_address.is_default)
        self.assertTrue(second_address.is_default)
        self.assertEqual(default_response.data["default_shipping"]["id"], second_address.id)

        delete_response = self.client.delete(
            reverse("shipping_address_detail", args=[second_address.id]),
            format="json",
        )
        first_address.refresh_from_db()

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertTrue(first_address.is_default)
        self.assertEqual(delete_response.data["default_shipping"]["id"], first_address.id)
        self.assertEqual(len(delete_response.data["shipping_addresses"]), 1)

    def test_checkout_accepts_saved_shipping_address_id(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Guardado",
            email=user.email,
            phone="3001234567",
        )
        address = ShippingAddress.objects.create(
            customer=customer,
            label="Casa",
            name="Cliente Guardado",
            phone="3001234567",
            address="Calle Guardada",
            city="Medellin",
            notes="Timbre 2",
            is_default=True,
        )
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 1})

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingAddressId": address.id,
                "ageConfirmed": True,
            },
            format="json",
        )
        order = Order.objects.get(id=response.data["order_id"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(order.shipping_name, "Cliente Guardado")
        self.assertEqual(order.shipping_phone, "3001234567")
        self.assertEqual(order.shipping_address, "Calle Guardada")
        self.assertEqual(order.shipping_city, "Medellin")
        self.assertEqual(order.shipping_notes, "Timbre 2")

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

    def test_login_rejects_malformed_identifier_without_error(self):
        response = self.client.post(
            reverse("auth_login"),
            {
                "email": {"valor": "no-valido"},
                "password": "ClaveIncorrecta123",
            },
            format="json",
        )

        event = EventLog.objects.get(event_type="auth_login_failed")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Credenciales invalidas")
        self.assertEqual(event.metadata["identifier_type"], "username")

    def test_login_rejects_malformed_password_without_error(self):
        self.create_user()

        response = self.client.post(
            reverse("auth_login"),
            {
                "email": "cliente",
                "password": {"valor": "no-valido"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Faltan campos")
        self.assertTrue(
            EventLog.objects.filter(event_type="auth_login_failed").exists()
        )

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
        category = Category.objects.create(
            name="Desechables",
            slug="desechables",
            description="Vapes listos para usar.",
        )
        newest_product = Product.objects.create(
            name="Producto nuevo",
            category=category,
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
        self.assertEqual(response.data[0]["category"]["slug"], "desechables")
        self.assertEqual(response.data[0]["category"]["name"], "Desechables")

    def test_categories_api_returns_only_active_categories(self):
        active_category = Category.objects.create(
            name="Pods",
            slug="pods",
            description="Pods y dispositivos recargables.",
        )
        inactive_category = Category.objects.create(
            name="Oculta",
            slug="oculta",
            is_active=False,
        )
        hidden_category_product = Product.objects.create(
            name="Producto con categoria oculta",
            category=inactive_category,
            description="Debe mostrarse sin categoria.",
            price=Decimal("12.00"),
            stock=2,
        )

        response = self.client.get(reverse("api_categories"))
        category_ids = [category["id"] for category in response.data]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(active_category.id, category_ids)
        self.assertNotIn(inactive_category.id, category_ids)
        self.assertNotIn("is_active", response.data[0])

        products_response = self.client.get(reverse("api_products"))
        hidden_product = next(
            product
            for product in products_response.data
            if product["id"] == hidden_category_product.id
        )

        self.assertIsNone(hidden_product["category"])

    def test_category_generates_unique_slug_when_missing(self):
        first_category = Category.objects.create(name="Pods Premium")
        second_category = Category.objects.create(name="Pods-Premium")

        self.assertEqual(first_category.slug, "pods-premium")
        self.assertEqual(second_category.slug, "pods-premium-2")

    def test_products_api_filters_by_query_params(self):
        pods_category = Category.objects.create(name="Pods", slug="pods")
        disposables_category = Category.objects.create(
            name="Desechables",
            slug="desechables",
        )
        first_product = Product.objects.create(
            name="Pod Economico",
            category=pods_category,
            description="Dispositivo recargable sencillo.",
            price=Decimal("30.00"),
            stock=2,
        )
        second_product = Product.objects.create(
            name="Pod Premium",
            category=pods_category,
            description="Dispositivo recargable avanzado.",
            price=Decimal("70.00"),
            stock=8,
        )
        Product.objects.create(
            name="Desechable Frutal",
            category=disposables_category,
            description="Producto listo para usar.",
            price=Decimal("45.00"),
            stock=5,
        )

        response = self.client.get(
            reverse("api_products"),
            {
                "q": "recargable",
                "category": "pods",
                "stock": "available",
                "ordering": "price-asc",
            },
        )
        product_ids = [product["id"] for product in response.data]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(product_ids, [first_product.id, second_product.id])

    def test_products_api_filters_low_and_empty_stock(self):
        Product.objects.create(
            name="Producto bajo stock",
            description="Debe aparecer como ultimas unidades.",
            price=Decimal("20.00"),
            stock=3,
        )
        Product.objects.create(
            name="Producto sin stock",
            description="Debe aparecer sin disponibilidad.",
            price=Decimal("18.00"),
            stock=0,
        )

        low_response = self.client.get(reverse("api_products"), {"stock": "low"})
        empty_response = self.client.get(reverse("api_products"), {"stock": "empty"})

        self.assertEqual(low_response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            all(0 < product["stock"] <= 3 for product in low_response.data)
        )
        self.assertEqual(empty_response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            all(product["stock"] == 0 for product in empty_response.data)
        )

    def test_products_api_rejects_invalid_query_params(self):
        invalid_stock_response = self.client.get(
            reverse("api_products"),
            {"stock": "agotados"},
        )
        invalid_ordering_response = self.client.get(
            reverse("api_products"),
            {"ordering": "fecha-desc"},
        )
        invalid_page_response = self.client.get(
            reverse("api_products"),
            {"page": "0"},
        )
        invalid_page_size_response = self.client.get(
            reverse("api_products"),
            {"page_size": "100"},
        )

        self.assertEqual(
            invalid_stock_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_ordering_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_page_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_page_size_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_products_api_paginates_when_requested(self):
        for index in range(8):
            Product.objects.create(
                name=f"Producto pagina {index}",
                description="Producto usado para probar paginacion.",
                price=Decimal("12.00"),
                stock=5,
            )

        response = self.client.get(
            reverse("api_products"),
            {
                "page": "2",
                "page_size": "3",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 3)
        self.assertEqual(response.data["pagination"]["page"], 2)
        self.assertEqual(response.data["pagination"]["page_size"], 3)
        self.assertEqual(response.data["pagination"]["total"], 9)
        self.assertEqual(response.data["pagination"]["total_pages"], 3)
        self.assertTrue(response.data["pagination"]["has_next"])
        self.assertTrue(response.data["pagination"]["has_previous"])

    def test_products_api_paginates_filtered_results(self):
        for index in range(5):
            Product.objects.create(
                name=f"Pod filtrado {index}",
                description="Producto recargable para paginacion filtrada.",
                price=Decimal("32.00"),
                stock=3,
            )

        response = self.client.get(
            reverse("api_products"),
            {
                "q": "recargable",
                "stock": "low",
                "page": "2",
                "page_size": "2",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["pagination"]["page"], 2)
        self.assertEqual(response.data["pagination"]["total"], 5)
        self.assertEqual(response.data["pagination"]["total_pages"], 3)

    def test_favorite_endpoints_require_authentication(self):
        responses = [
            self.client.get(reverse("favorite_products")),
            self.client.post(
                reverse("toggle_favorite_product"),
                {"productId": self.product.id},
                format="json",
            ),
        ]

        for response in responses:
            self.assertIn(
                response.status_code,
                (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
            )

    def test_user_can_toggle_and_list_favorites(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")

        add_response = self.client.post(
            reverse("toggle_favorite_product"),
            {"productId": self.product.id},
            format="json",
        )

        self.assertEqual(add_response.status_code, status.HTTP_200_OK)
        self.assertTrue(add_response.data["is_favorite"])
        self.assertEqual(FavoriteProduct.objects.count(), 1)

        list_response = self.client.get(reverse("favorite_products"))

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(list_response.data["favorites"][0]["id"], self.product.id)
        self.assertTrue(list_response.data["favorites"][0]["is_favorite"])

        remove_response = self.client.post(
            reverse("toggle_favorite_product"),
            {"productId": self.product.id},
            format="json",
        )

        self.assertEqual(remove_response.status_code, status.HTTP_200_OK)
        self.assertFalse(remove_response.data["is_favorite"])
        self.assertEqual(FavoriteProduct.objects.count(), 0)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="favorite_added",
                metadata__product_id=self.product.id,
            ).exists()
        )
        self.assertTrue(
            EventLog.objects.filter(
                event_type="favorite_removed",
                metadata__product_id=self.product.id,
            ).exists()
        )

    def test_favorites_reject_invalid_or_inactive_product(self):
        user = self.create_user()
        inactive_product = Product.objects.create(
            name="Producto inactivo",
            description="No debe guardarse como favorito.",
            price=Decimal("11.00"),
            stock=2,
            is_active=False,
        )
        self.client.login(username=user.username, password="ClaveSegura123")

        invalid_response = self.client.post(
            reverse("toggle_favorite_product"),
            {"productId": "abc"},
            format="json",
        )
        inactive_response = self.client.post(
            reverse("toggle_favorite_product"),
            {"productId": inactive_product.id},
            format="json",
        )

        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(inactive_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(FavoriteProduct.objects.count(), 0)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="favorite_failed",
                metadata__product_id=inactive_product.id,
            ).exists()
        )

    def test_products_api_marks_authenticated_favorites(self):
        user = self.create_user()
        FavoriteProduct.objects.create(user=user, product=self.product)
        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.get(reverse("api_products"))
        favorite_product = next(
            product
            for product in response.data
            if product["id"] == self.product.id
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(favorite_product["is_favorite"])

    def test_review_submit_requires_authentication(self):
        response = self.client.post(
            reverse("submit_product_review", args=[self.product.id]),
            {
                "rating": 5,
                "comment": "Muy buen producto.",
            },
            format="json",
        )

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_user_can_create_update_and_list_product_review(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")

        create_response = self.client.post(
            reverse("submit_product_review", args=[self.product.id]),
            {
                "rating": 5,
                "comment": "Excelente sabor.",
            },
            format="json",
        )
        update_response = self.client.post(
            reverse("submit_product_review", args=[self.product.id]),
            {
                "rating": 4,
                "comment": "Buen producto.",
            },
            format="json",
        )
        list_response = self.client.get(
            reverse("product_reviews", args=[self.product.id])
        )

        self.assertEqual(create_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(ProductReview.objects.count(), 1)
        self.assertEqual(update_response.data["review"]["rating"], 4)
        self.assertEqual(update_response.data["rating_average"], 4.0)
        self.assertEqual(update_response.data["rating_count"], 1)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["own_review"]["rating"], 4)
        self.assertEqual(list_response.data["reviews"][0]["comment"], "Buen producto.")
        self.assertTrue(
            EventLog.objects.filter(
                event_type="review_created",
                metadata__product_id=self.product.id,
            ).exists()
        )
        self.assertTrue(
            EventLog.objects.filter(
                event_type="review_updated",
                metadata__product_id=self.product.id,
            ).exists()
        )

    def test_product_reviews_reject_invalid_payload_and_inactive_product(self):
        user = self.create_user()
        inactive_product = Product.objects.create(
            name="Producto no reseñable",
            description="Producto inactivo.",
            price=Decimal("10.00"),
            stock=1,
            is_active=False,
        )
        self.client.login(username=user.username, password="ClaveSegura123")

        invalid_rating_response = self.client.post(
            reverse("submit_product_review", args=[self.product.id]),
            {
                "rating": 6,
                "comment": "Fuera de rango.",
            },
            format="json",
        )
        invalid_comment_response = self.client.post(
            reverse("submit_product_review", args=[self.product.id]),
            {
                "rating": 5,
                "comment": "x" * 601,
            },
            format="json",
        )
        inactive_response = self.client.post(
            reverse("submit_product_review", args=[inactive_product.id]),
            {
                "rating": 5,
                "comment": "No debe guardar.",
            },
            format="json",
        )

        self.assertEqual(
            invalid_rating_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_comment_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(inactive_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ProductReview.objects.count(), 0)

    def test_products_api_includes_review_summary(self):
        first_user = self.create_user()
        second_user = User.objects.create_user(
            username="cliente_reviews",
            email="cliente_reviews@example.com",
            password="ClaveSegura123",
        )
        ProductReview.objects.create(
            user=first_user,
            product=self.product,
            rating=5,
            comment="Muy bueno.",
        )
        ProductReview.objects.create(
            user=second_user,
            product=self.product,
            rating=3,
            comment="Correcto.",
        )

        response = self.client.get(reverse("api_products"))
        product_data = next(
            product
            for product in response.data
            if product["id"] == self.product.id
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(product_data["rating_average"], 4.0)
        self.assertEqual(product_data["rating_count"], 2)

    def test_authenticated_product_api_is_not_cached(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.get(reverse("api_products"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.headers["Cache-Control"], "no-store, max-age=0")

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

    def test_cart_coupon_apply_remove_and_discount_total(self):
        DiscountCode.objects.create(
            code="VAPE10",
            discount_type="percent",
            value=Decimal("10.00"),
        )
        self.set_session_cart({str(self.product.id): 2})

        apply_response = self.client.post(
            reverse("api_cart_apply_coupon"),
            {"code": " vape10 "},
            format="json",
        )
        cart_response = self.client.get(reverse("api_cart"))
        remove_response = self.client.post(reverse("api_cart_remove_coupon"))

        self.assertEqual(apply_response.status_code, status.HTTP_200_OK)
        self.assertEqual(apply_response.data["subtotal"], 20.0)
        self.assertEqual(apply_response.data["discount"], 2.0)
        self.assertEqual(apply_response.data["total"], 18.0)
        self.assertEqual(apply_response.data["coupon"]["code"], "VAPE10")
        self.assertEqual(cart_response.data["total"], 18.0)
        self.assertEqual(cart_response.data["coupon"]["code"], "VAPE10")
        self.assertEqual(remove_response.status_code, status.HTTP_200_OK)
        self.assertEqual(remove_response.data["discount"], 0.0)
        self.assertEqual(remove_response.data["total"], 20.0)
        self.assertIsNone(remove_response.data["coupon"])

    def test_cart_coupon_rejects_invalid_or_minimum_total(self):
        DiscountCode.objects.create(
            code="MINIMO",
            discount_type="fixed",
            value=Decimal("5.00"),
            min_order_total=Decimal("50.00"),
        )
        self.set_session_cart({str(self.product.id): 2})

        invalid_response = self.client.post(
            reverse("api_cart_apply_coupon"),
            {"code": "NOEXISTE"},
            format="json",
        )
        minimum_response = self.client.post(
            reverse("api_cart_apply_coupon"),
            {"code": "MINIMO"},
            format="json",
        )

        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(minimum_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("compra minima", minimum_response.data["error"])

    def test_cart_update_sets_exact_quantity(self):
        self.set_session_cart({str(self.product.id): 1})

        response = self.client.post(
            reverse("api_cart_update"),
            {
                "productId": self.product.id,
                "quantity": 3,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["cart"][str(self.product.id)], 3)
        self.assertEqual(self.client.session.get("cart")[str(self.product.id)], 3)

    def test_cart_update_removes_item_when_quantity_is_zero(self):
        self.set_session_cart({str(self.product.id): 2})

        response = self.client.post(
            reverse("api_cart_update"),
            {
                "productId": self.product.id,
                "quantity": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["cart"], {})
        self.assertEqual(self.client.session.get("cart"), {})

    def test_cart_update_rejects_invalid_quantity_and_stock_excess(self):
        invalid_quantities = (-1, "2.5", True, "abc")

        for invalid_quantity in invalid_quantities:
            response = self.client.post(
                reverse("api_cart_update"),
                {
                    "productId": self.product.id,
                    "quantity": invalid_quantity,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            reverse("api_cart_update"),
            {
                "productId": self.product.id,
                "quantity": 6,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_cart_cleans_malformed_session_payload(self):
        self.set_session_cart(["carrito", "invalido"])

        response = self.client.get(reverse("api_cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total"], 0)
        self.assertEqual(self.client.session.get("cart"), {})

    def test_cart_normalizes_legacy_session_item(self):
        self.set_session_cart({self.product.id: "2"})

        response = self.client.get(reverse("api_cart"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"][0]["quantity"], 2)
        self.assertEqual(self.client.session.get("cart"), {str(self.product.id): 2})

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

    def test_checkout_rejects_malformed_session_cart_without_error(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart(123)

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

        event = EventLog.objects.get(event_type="checkout_failed")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["cart_updated"])
        self.assertEqual(self.client.session.get("cart"), {})
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(event.metadata["cart_payload_type"], "int")

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
        history = order.status_history.get()
        self.assertEqual(history.status, "pagado")
        self.assertEqual(history.previous_status, "")
        self.assertEqual(history.changed_by, user)
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
            orders_response.data["orders"][0]["status_history"][0]["status"],
            "pagado",
        )
        self.assertEqual(
            orders_response.data["orders"][0]["status_history"][0]["note"],
            "Pedido creado desde checkout.",
        )
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

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="no-reply@example.com",
        ORDER_NOTIFICATION_EMAIL="orders@example.com",
    )
    def test_checkout_sends_customer_and_admin_order_notifications(self):
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
                "shippingNotes": "Porteria",
                "ageConfirmed": True,
            },
            format="json",
        )
        order = Order.objects.get(id=response.data["order_id"])
        subjects = [email.subject for email in mail.outbox]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn(f"Pedido #{order.id} recibido en Vape Shop", subjects)
        self.assertIn(f"Nuevo pedido #{order.id} en Vape Shop", subjects)
        self.assertIn(user.email, mail.outbox[0].to + mail.outbox[1].to)
        self.assertIn("orders@example.com", mail.outbox[0].to + mail.outbox[1].to)
        self.assertEqual(
            response.data["notifications"],
            {
                "customer_email_sent": True,
                "admin_email_sent": True,
            },
        )
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_notification_sent",
                metadata__order_id=order.id,
                metadata__customer_email_sent=True,
                metadata__admin_email_sent=True,
            ).exists()
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="no-reply@example.com",
        ORDER_NOTIFICATION_EMAIL="",
    )
    def test_checkout_continues_if_order_admin_notification_is_missing(self):
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
                "ageConfirmed": True,
            },
            format="json",
        )
        order = Order.objects.get(id=response.data["order_id"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertEqual(
            response.data["notifications"],
            {
                "customer_email_sent": True,
                "admin_email_sent": False,
            },
        )
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_notification_partial",
                metadata__order_id=order.id,
                metadata__customer_email_sent=True,
                metadata__admin_email_sent=False,
            ).exists()
        )

    def test_checkout_applies_coupon_and_stores_discount_snapshot(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 2})
        discount = DiscountCode.objects.create(
            code="AHORRO5",
            discount_type="fixed",
            value=Decimal("5.00"),
        )
        self.client.post(
            reverse("api_cart_apply_coupon"),
            {"code": "AHORRO5"},
            format="json",
        )

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingName": "Cliente Prueba",
                "shippingPhone": "3001234567",
                "shippingAddress": "Calle 1",
                "shippingCity": "Medellin",
                "shippingNotes": "",
                "ageConfirmed": True,
            },
            format="json",
        )

        order = Order.objects.get(id=response.data["order_id"])
        discount.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["subtotal"], 20.0)
        self.assertEqual(response.data["discount"], 5.0)
        self.assertEqual(response.data["total_pagado"], 15.0)
        self.assertEqual(response.data["coupon_code"], "AHORRO5")
        self.assertEqual(order.coupon_code, "AHORRO5")
        self.assertEqual(order.subtotal_amount, Decimal("20.00"))
        self.assertEqual(order.discount_amount, Decimal("5.00"))
        self.assertEqual(order.total_amount, Decimal("15.00"))
        self.assertEqual(discount.used_count, 1)
        self.assertEqual(self.product.stock, 3)

        detail_response = self.client.get(reverse("order_detail", args=[order.id]))

        self.assertEqual(detail_response.data["subtotal"], 20.0)
        self.assertEqual(detail_response.data["discount"], 5.0)
        self.assertEqual(detail_response.data["total"], 15.0)
        self.assertEqual(detail_response.data["coupon_code"], "AHORRO5")

    def test_checkout_rejects_coupon_that_becomes_invalid(self):
        user = self.create_user()
        self.client.login(username=user.username, password="ClaveSegura123")
        self.set_session_cart({str(self.product.id): 2})
        DiscountCode.objects.create(
            code="AGOTADO",
            discount_type="percent",
            value=Decimal("10.00"),
            max_uses=1,
            used_count=1,
        )
        session = self.client.session
        session["coupon_code"] = "AGOTADO"
        session.save()

        response = self.client.post(
            reverse("checkout"),
            {
                "shippingName": "Cliente Prueba",
                "shippingPhone": "3001234567",
                "shippingAddress": "Calle 1",
                "shippingCity": "Medellin",
                "shippingNotes": "",
                "ageConfirmed": True,
            },
            format="json",
        )

        self.product.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["coupon_invalid"])
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.product.stock, 5)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="checkout_failed",
                metadata__coupon_code="AGOTADO",
            ).exists()
        )

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
        reorder_response = self.client.post(reverse("reorder_order", args=[order.id]))

        self.assertEqual(orders_response.status_code, status.HTTP_200_OK)
        self.assertEqual(orders_response.data["orders"], [])
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(cancel_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(reorder_response.status_code, status.HTTP_404_NOT_FOUND)

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
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_reorder_failed",
                metadata__order_id=order.id,
            ).exists()
        )

    def test_user_can_view_own_order_detail(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Detalle",
            email=user.email,
        )
        order = Order.objects.create(
            customer=customer,
            status="enviado",
            completed=True,
            shipping_name="Cliente Detalle",
            shipping_phone="3001234567",
            shipping_address="Calle 123",
            shipping_city="Medellin",
            shipping_notes="Porteria",
            tracking_carrier="Servientrega",
            tracking_number="GUIA123",
            tracking_url="https://example.com/rastreo/GUIA123",
            age_verified=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
        )
        OrderStatusHistory.objects.create(
            order=order,
            previous_status="pagado",
            status="enviado",
            changed_by=user,
            note="Pedido enviado por transportadora.",
        )

        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.get(reverse("order_detail", args=[order.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], order.id)
        self.assertEqual(response.data["status"], "enviado")
        self.assertEqual(response.data["total"], 20.0)
        self.assertEqual(response.data["shipping"]["city"], "Medellin")
        self.assertEqual(response.data["shipping"]["notes"], "Porteria")
        self.assertEqual(response.data["tracking"]["carrier"], "Servientrega")
        self.assertEqual(response.data["tracking"]["number"], "GUIA123")
        self.assertEqual(
            response.data["tracking"]["url"],
            "https://example.com/rastreo/GUIA123",
        )
        self.assertEqual(response.data["items"][0]["product"]["name"], self.product.name)
        self.assertEqual(response.data["items"][0]["quantity"], 2)
        self.assertEqual(response.data["items"][0]["line_total"], 20.0)
        self.assertEqual(response.data["status_history"][0]["previous_status"], "pagado")
        self.assertEqual(response.data["status_history"][0]["status"], "enviado")
        self.assertEqual(
            response.data["status_history"][0]["note"],
            "Pedido enviado por transportadora.",
        )

    def test_reorder_adds_available_items_to_cart(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Recompra",
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

        response = self.client.post(reverse("reorder_order", args=[order.id]))
        session_cart = self.client.session.get("cart", {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["ok"])
        self.assertEqual(session_cart[str(self.product.id)], 2)
        self.assertEqual(response.data["added_items"][0]["quantity"], 2)
        self.assertEqual(response.data["skipped_items"], [])
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_reorder_success",
                metadata__order_id=order.id,
            ).exists()
        )

    def test_reorder_rejects_when_no_items_are_available(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Recompra",
            email=user.email,
        )
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        order = Order.objects.create(
            customer=customer,
            status="entregado",
            completed=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
        )

        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.post(reverse("reorder_order", args=[order.id]))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("disponibles", response.data["error"])
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_my_orders_paginates_results(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Paginado",
            email=user.email,
        )

        for _ in range(6):
            order = Order.objects.create(
                customer=customer,
                status="pagado",
                completed=True,
            )
            OrderItem.objects.create(
                order=order,
                product=self.product,
                quantity=1,
            )

        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.get(
            reverse("my_orders"),
            {
                "page": "2",
                "page_size": "2",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["orders"]), 2)
        self.assertEqual(response.data["pagination"]["page"], 2)
        self.assertEqual(response.data["pagination"]["page_size"], 2)
        self.assertEqual(response.data["pagination"]["total"], 6)
        self.assertEqual(response.data["pagination"]["total_pages"], 3)
        self.assertTrue(response.data["pagination"]["has_next"])
        self.assertTrue(response.data["pagination"]["has_previous"])

    def test_my_orders_filters_by_status(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Filtrado",
            email=user.email,
        )

        for order_status in ("pagado", "enviado", "cancelado"):
            order = Order.objects.create(
                customer=customer,
                status=order_status,
                completed=True,
            )
            OrderItem.objects.create(
                order=order,
                product=self.product,
                quantity=1,
            )

        self.client.login(username=user.username, password="ClaveSegura123")

        response = self.client.get(
            reverse("my_orders"),
            {
                "status": "enviado",
                "page": "1",
                "page_size": "4",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["orders"]), 1)
        self.assertEqual(response.data["orders"][0]["status"], "enviado")
        self.assertEqual(response.data["pagination"]["total"], 1)

    def test_my_orders_rejects_invalid_pagination(self):
        user = self.create_user()
        Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Paginado",
            email=user.email,
        )

        self.client.login(username=user.username, password="ClaveSegura123")

        invalid_page_response = self.client.get(
            reverse("my_orders"),
            {"page": "0"},
        )
        invalid_page_size_response = self.client.get(
            reverse("my_orders"),
            {"page_size": "100"},
        )
        invalid_status_response = self.client.get(
            reverse("my_orders"),
            {"status": "desconocido"},
        )

        self.assertEqual(
            invalid_page_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_page_size_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            invalid_status_response.status_code,
            status.HTTP_400_BAD_REQUEST,
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
        history = order.status_history.get()
        self.assertEqual(history.previous_status, "pagado")
        self.assertEqual(history.status, "cancelado")
        self.assertEqual(history.changed_by, user)
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
            tracking_carrier="Interrapidisimo",
            tracking_number="IR123",
            tracking_url="https://example.com/IR123",
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
        self.assertIn("Interrapidisimo", content)
        self.assertIn("IR123", content)
        self.assertIn("20.00", content)

    def test_admin_business_dashboard_context_summarizes_metrics(self):
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        second_product = Product.objects.create(
            name="Producto destacado",
            description="Descripcion",
            price=Decimal("15.00"),
            stock=2,
        )
        paid_order = Order.objects.create(
            customer=customer,
            status="pagado",
            completed=True,
            total_amount=Decimal("20.00"),
        )
        sent_order = Order.objects.create(
            customer=customer,
            status="enviado",
            completed=True,
            total_amount=Decimal("45.00"),
        )
        Order.objects.create(
            customer=customer,
            status="cancelado",
            completed=False,
            total_amount=Decimal("99.00"),
        )
        OrderItem.objects.create(
            order=paid_order,
            product=self.product,
            quantity=2,
        )
        OrderItem.objects.create(
            order=sent_order,
            product=second_product,
            quantity=3,
        )

        context = build_business_dashboard_context()
        status_counts = {
            row["status"]: row["count"]
            for row in context["status_rows"]
        }

        self.assertEqual(context["total_orders"], 3)
        self.assertEqual(context["orders_last_30_days"], 3)
        self.assertEqual(context["revenue_total"], Decimal("65.00"))
        self.assertEqual(context["average_order_value"], Decimal("32.50"))
        self.assertEqual(context["customer_count"], 1)
        self.assertEqual(status_counts["pagado"], 1)
        self.assertEqual(status_counts["enviado"], 1)
        self.assertEqual(status_counts["cancelado"], 1)
        self.assertEqual(context["top_products"][0]["product_name"], "Producto destacado")
        self.assertEqual(context["top_products"][0]["units_sold"], 3)
        self.assertIn(second_product, list(context["low_stock_products"]))

    def test_admin_business_dashboard_view_requires_staff_and_renders(self):
        dashboard_url = reverse("admin:store_business_dashboard")

        anonymous_response = self.client.get(dashboard_url)

        self.assertEqual(anonymous_response.status_code, 302)

        admin_user = User.objects.create_superuser(
            username="dashboard-admin",
            email="dashboard-admin@example.com",
            password="ClaveSegura123",
        )
        self.client.force_login(admin_user)

        response = self.client.get(dashboard_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumen del negocio")
        self.assertContains(response, "Productos mas vendidos")
        self.assertContains(response, "Descargar ventas CSV")

    def test_admin_business_dashboard_exports_filtered_reports(self):
        now = timezone.now()
        old_date = now - timedelta(days=45)
        user = self.create_user()
        customer = Customer.objects.create(
            user=user,
            first_name="Cliente",
            last_name="Prueba",
            email=user.email,
        )
        formula_product = Product.objects.create(
            name="=Producto reporte",
            description="Descripcion",
            price=Decimal("12.00"),
            stock=5,
        )
        included_order = Order.objects.create(
            customer=customer,
            status="pagado",
            completed=True,
            shipping_city="Medellin",
            subtotal_amount=Decimal("24.00"),
            total_amount=Decimal("24.00"),
        )
        old_order = Order.objects.create(
            customer=customer,
            status="pagado",
            completed=True,
            shipping_city="Envigado",
            subtotal_amount=Decimal("10.00"),
            total_amount=Decimal("10.00"),
        )
        cancelled_order = Order.objects.create(
            customer=customer,
            status="cancelado",
            completed=False,
            shipping_city="Medellin",
            subtotal_amount=Decimal("99.00"),
            total_amount=Decimal("99.00"),
        )
        Order.objects.filter(id=included_order.id).update(date_ordered=now)
        Order.objects.filter(id=old_order.id).update(date_ordered=old_date)
        Order.objects.filter(id=cancelled_order.id).update(date_ordered=now)
        OrderItem.objects.create(
            order=included_order,
            product=formula_product,
            quantity=2,
        )
        OrderItem.objects.create(
            order=old_order,
            product=self.product,
            quantity=1,
        )
        OrderItem.objects.create(
            order=cancelled_order,
            product=self.product,
            quantity=4,
        )
        admin_user = User.objects.create_superuser(
            username="report-admin",
            email="report-admin@example.com",
            password="ClaveSegura123",
        )
        report_params = {
            "date_from": now.date().isoformat(),
            "date_to": now.date().isoformat(),
        }
        self.client.force_login(admin_user)

        sales_response = self.client.get(
            reverse("admin:store_business_sales_report"),
            report_params,
        )
        sales_content = sales_response.content.decode()

        self.assertEqual(sales_response.status_code, 200)
        self.assertIn(
            "reporte-ventas.csv",
            sales_response["Content-Disposition"],
        )
        self.assertIn(f"\r\n{included_order.id},", sales_content)
        self.assertIn("Medellin", sales_content)
        self.assertNotIn(f"\r\n{old_order.id},", sales_content)
        self.assertNotIn(f"\r\n{cancelled_order.id},", sales_content)

        products_response = self.client.get(
            reverse("admin:store_business_products_report"),
            report_params,
        )
        products_content = products_response.content.decode()

        self.assertEqual(products_response.status_code, 200)
        self.assertIn(
            "reporte-productos-vendidos.csv",
            products_response["Content-Disposition"],
        )
        self.assertIn("'=Producto reporte", products_content)
        self.assertIn("2", products_content)
        self.assertNotIn("Producto prueba", products_content)

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
        request = self.create_admin_request()

        admin_model.mark_as_preparing(
            request,
            Order.objects.filter(id=order.id),
        )

        order.refresh_from_db()
        self.assertEqual(order.status, "en_preparacion")
        self.assertTrue(order.completed)
        first_history = order.status_history.get(status="en_preparacion")
        self.assertEqual(first_history.previous_status, "pagado")
        self.assertEqual(first_history.changed_by, request.user)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="admin_order_preparing",
                metadata__order_id=order.id,
            ).exists()
        )

        admin_model.mark_as_refunded(
            request,
            Order.objects.filter(id=order.id),
        )

        order.refresh_from_db()
        self.assertEqual(order.status, "reembolsado")
        self.assertFalse(order.completed)
        second_history = order.status_history.get(status="reembolsado")
        self.assertEqual(second_history.previous_status, "en_preparacion")
        self.assertEqual(order.status_history.count(), 2)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="admin_order_refunded",
                metadata__order_id=order.id,
            ).exists()
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="no-reply@example.com",
    )
    def test_admin_status_actions_set_tracking_dates_and_notify_customer(self):
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
            tracking_carrier="Interrapidisimo",
            tracking_number="IR123",
            tracking_url="https://tracking.example.com/IR123",
        )
        admin_model = OrderAdmin(Order, self.admin_site)
        admin_model.message_user = lambda *args, **kwargs: None
        request = self.create_admin_request()

        admin_model.mark_as_sent(
            request,
            Order.objects.filter(id=order.id),
        )

        order.refresh_from_db()
        self.assertEqual(order.status, "enviado")
        self.assertIsNotNone(order.shipped_at)
        self.assertIsNone(order.delivered_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            f"Actualizacion de pedido #{order.id}: Enviado",
            mail.outbox[0].subject,
        )
        self.assertIn("Interrapidisimo", mail.outbox[0].body)
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_status_notification_sent",
                metadata__order_id=order.id,
                metadata__new_status="enviado",
            ).exists()
        )

        shipped_at = order.shipped_at

        admin_model.mark_as_delivered(
            request,
            Order.objects.filter(id=order.id),
        )

        order.refresh_from_db()
        self.assertEqual(order.status, "entregado")
        self.assertEqual(order.shipped_at, shipped_at)
        self.assertIsNotNone(order.delivered_at)
        self.assertEqual(order.status_history.count(), 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn(
            f"Actualizacion de pedido #{order.id}: Entregado",
            mail.outbox[1].subject,
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="no-reply@example.com",
    )
    def test_admin_save_model_notifies_status_change_to_sent(self):
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
        admin_model = OrderAdmin(Order, self.admin_site)
        request = self.create_admin_request()

        order.status = "enviado"
        admin_model.save_model(request, order, form=None, change=True)
        order.refresh_from_db()

        self.assertEqual(order.status, "enviado")
        self.assertIsNotNone(order.shipped_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            f"Actualizacion de pedido #{order.id}: Enviado",
            mail.outbox[0].subject,
        )
        self.assertTrue(
            EventLog.objects.filter(
                event_type="order_status_notification_sent",
                metadata__order_id=order.id,
                metadata__previous_status="en_preparacion",
                metadata__new_status="enviado",
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

    @override_settings(TRUST_X_FORWARDED_FOR=True)
    def test_log_event_ignores_invalid_client_ip(self):
        request = self.request_factory.get(
            "/api/contact/",
            HTTP_X_FORWARDED_FOR="ip-invalida, 127.0.0.1",
        )

        event = log_event(
            "security_test",
            "Evento con IP invalida.",
            request=request,
        )

        self.assertIsNotNone(event)
        self.assertIsNone(event.ip_address)

    @override_settings(TRUST_X_FORWARDED_FOR=True)
    def test_get_client_ip_uses_first_valid_forwarded_ip(self):
        request = self.request_factory.get(
            "/api/contact/",
            HTTP_X_FORWARDED_FOR="192.0.2.10, 127.0.0.1",
        )

        self.assertEqual(get_client_ip(request), "192.0.2.10")

    @override_settings(TRUST_X_FORWARDED_FOR=False)
    def test_get_client_ip_ignores_forwarded_ip_by_default(self):
        request = self.request_factory.get(
            "/api/contact/",
            HTTP_X_FORWARDED_FOR="192.0.2.10",
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertEqual(get_client_ip(request), "127.0.0.1")

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
