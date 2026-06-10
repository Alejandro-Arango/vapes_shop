"""
Archivo: tests.py
Descripcion: Define pruebas automatizadas para los flujos principales de autenticacion, carrito, checkout y cancelacion.
Dependencias: Django test, Django auth, Django urls, Django REST Framework y modelos de store
"""

from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.core import mail
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import RequestFactory, override_settings
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from .admin import ContactLeadAdmin, EventLogAdmin, OrderAdmin
from .models import ContactLead, Customer, EventLog, Order, OrderItem, Product


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
        self.assertTrue(
            EventLog.objects.filter(event_type="auth_login_failed").exists()
        )

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
        self.assertTrue(
            EventLog.objects.filter(
                event_type="contact_received",
                metadata__lead_id=lead.id,
            ).exists()
        )

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
        self.assertEqual(item.unit_price, Decimal("10.00"))
        self.assertTrue(
            EventLog.objects.filter(
                event_type="checkout_success",
                metadata__order_id=order.id,
            ).exists()
        )

        self.product.price = Decimal("99.00")
        self.product.save(update_fields=["price"])

        orders_response = self.client.get(reverse("my_orders"))

        self.assertEqual(orders_response.status_code, status.HTTP_200_OK)
        self.assertEqual(orders_response.data["orders"][0]["status"], "pagado")
        self.assertEqual(orders_response.data["orders"][0]["status_label"], "Pagado")
        self.assertEqual(orders_response.data["orders"][0]["total"], 20.0)
        self.assertEqual(
            orders_response.data["orders"][0]["items"][0]["product"]["price"],
            10.0,
        )
        self.assertEqual(
            orders_response.data["orders"][0]["items"][0]["line_total"],
            20.0,
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

        admin_model.mark_as_refunded(
            self.create_admin_request(),
            Order.objects.filter(id=order.id),
        )

        order.refresh_from_db()
        self.assertEqual(order.status, "reembolsado")
        self.assertFalse(order.completed)

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
