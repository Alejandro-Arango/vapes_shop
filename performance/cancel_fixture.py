#!/usr/bin/env python3
"""
Prepara y verifica cancelaciones concurrentes de una misma orden pagada.
La utilidad solo opera sobre una base efimera marcada para rendimiento.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4


USER_PREFIX = "load-cancel-"
CATEGORY_NAME = "Carga cancelacion"
PRODUCT_NAME = "Producto cancelacion concurrente"
PURCHASED_QUANTITY = 2
STOCK_BEFORE_CHECKOUT = 5
STOCK_AFTER_CHECKOUT = STOCK_BEFORE_CHECKOUT - PURCHASED_QUANTITY


def configure_django():
    project_root = Path(
        os.environ.get(
            "DJANGO_PROJECT_ROOT",
            Path(__file__).resolve().parents[1] / "backend",
        )
    ).resolve()
    sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mi_tienda.settings")

    import django

    django.setup()


def ensure_safe_database():
    from django.conf import settings

    enabled = os.environ.get("CHECKOUT_LOAD_TEST_ENABLED", "").lower()
    database_name = str(settings.DATABASES["default"]["NAME"])

    if enabled != "true":
        raise RuntimeError(
            "Define CHECKOUT_LOAD_TEST_ENABLED=true para usar esta utilidad."
        )

    if "performance" not in database_name.lower():
        raise RuntimeError(
            "La base de datos debe incluir 'performance' en su nombre."
        )


def write_json(path, payload):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_path.chmod(0o644)


def prepare_fixture(request_count, output_path):
    from django.conf import settings
    from django.contrib.auth.models import User
    from django.test import Client

    from store.models import Category, Customer, Order, OrderItem, Product, StockMovement
    from store.order_status import record_order_status

    if request_count < 2:
        raise RuntimeError("request_count debe ser al menos 2.")

    if User.objects.filter(username__startswith=USER_PREFIX).exists():
        raise RuntimeError("La base ya contiene usuarios de cancelacion.")

    category = Category.objects.create(
        name=CATEGORY_NAME,
        description="Datos efimeros para cancelacion concurrente.",
    )
    product = Product.objects.create(
        name=PRODUCT_NAME,
        category=category,
        description="Producto efimero ya descontado por checkout.",
        price="25.00",
        stock=STOCK_AFTER_CHECKOUT,
    )
    user = User.objects.create_user(
        username=f"{USER_PREFIX}001",
        email=f"{USER_PREFIX}001@example.invalid",
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])
    customer = Customer.objects.create(
        user=user,
        first_name="Cliente",
        last_name="Cancelacion",
        email=user.email,
    )
    order = Order.objects.create(
        customer=customer,
        checkout_token=uuid4(),
        completed=True,
        status="pagado",
        shipping_name="Cliente Cancelacion",
        shipping_phone="3001234567",
        shipping_address="Calle cancelacion",
        shipping_city="Medellin",
        age_verified=True,
        subtotal_amount="50.00",
        total_amount="50.00",
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        quantity=PURCHASED_QUANTITY,
        unit_price=product.price,
    )
    record_order_status(
        order,
        status="pagado",
        changed_by=user,
        note="Pedido preparado para cancelacion concurrente.",
    )
    StockMovement.objects.create(
        product=product,
        order=order,
        movement_type="checkout",
        quantity=-PURCHASED_QUANTITY,
        stock_before=STOCK_BEFORE_CHECKOUT,
        stock_after=STOCK_AFTER_CHECKOUT,
        user=user,
        reason="Salida efimera para prueba de cancelacion.",
    )

    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.get("/", HTTP_HOST="localhost")

    if response.status_code != 200:
        raise RuntimeError("No fue posible obtener CSRF para cancelacion.")

    session_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
    csrf_cookie = client.cookies.get(settings.CSRF_COOKIE_NAME)

    if session_cookie is None or csrf_cookie is None:
        raise RuntimeError("No se generaron cookies para cancelacion.")

    fixture = {
        "csrf_cookie_name": settings.CSRF_COOKIE_NAME,
        "csrf_token": csrf_cookie.value,
        "order_id": order.id,
        "product_id": product.id,
        "purchased_quantity": PURCHASED_QUANTITY,
        "request_count": request_count,
        "run_id": str(uuid4()),
        "session_cookie_name": settings.SESSION_COOKIE_NAME,
        "session_key": session_cookie.value,
        "stock_after_checkout": STOCK_AFTER_CHECKOUT,
        "stock_before_checkout": STOCK_BEFORE_CHECKOUT,
    }
    write_json(output_path, fixture)

    return {
        "order_id": order.id,
        "request_count": request_count,
        "run_id": fixture["run_id"],
    }


def build_verification(fixture):
    from store.models import EventLog, Order, OrderStatusHistory, Product, StockMovement

    order = Order.objects.get(id=fixture["order_id"])
    product = Product.objects.get(id=fixture["product_id"])
    restore_movements = StockMovement.objects.filter(
        order=order,
        product=product,
        movement_type="cancel_restore",
    )
    checkout_movements = StockMovement.objects.filter(
        order=order,
        product=product,
        movement_type="checkout",
    )
    cancel_history = OrderStatusHistory.objects.filter(
        order=order,
        previous_status="pagado",
        status="cancelado",
    )
    success_events = EventLog.objects.filter(
        event_type="order_cancel_success",
        metadata__order_id=order.id,
    ).count()
    failed_events = EventLog.objects.filter(
        event_type="order_cancel_failed",
        metadata__order_id=order.id,
    ).count()
    expected_rejections = int(fixture["request_count"]) - 1
    restore = restore_movements.first()

    checks = {
        "cancel_history_created_once": cancel_history.count() == 1,
        "checkout_movement_preserved": checkout_movements.count() == 1,
        "failed_events_match_rejections": (
            failed_events == expected_rejections
        ),
        "order_cancelled_once": (
            order.status == "cancelado" and order.completed is False
        ),
        "product_stock_restored_once": (
            product.stock == int(fixture["stock_before_checkout"])
        ),
        "restore_balance_is_exact": (
            restore is not None
            and restore.quantity == int(fixture["purchased_quantity"])
            and restore.stock_before == int(fixture["stock_after_checkout"])
            and restore.stock_after == int(fixture["stock_before_checkout"])
        ),
        "restore_movement_created_once": restore_movements.count() == 1,
        "success_event_created_once": success_events == 1,
    }
    return {
        "checks": checks,
        "details": {
            "cancel_history_count": cancel_history.count(),
            "checkout_movement_count": checkout_movements.count(),
            "failed_events": failed_events,
            "final_stock": product.stock,
            "order_completed": order.completed,
            "order_status": order.status,
            "restore_movement_count": restore_movements.count(),
            "success_events": success_events,
        },
        "ok": all(checks.values()),
        "run_id": fixture["run_id"],
    }


def verify_fixture(fixture_path, output_path):
    fixture = json.loads(
        Path(fixture_path).read_text(encoding="utf-8")
    )
    verification = build_verification(fixture)
    write_json(output_path, verification)

    if not verification["ok"]:
        failed_checks = [
            name
            for name, passed in verification["checks"].items()
            if not passed
        ]
        raise RuntimeError(
            "Fallaron invariantes: " + ", ".join(failed_checks)
        )

    return verification["details"]


def build_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--requests", type=int, required=True)
    prepare.add_argument("--output", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--fixture", required=True)
    verify.add_argument("--output", required=True)

    return parser


def main():
    args = build_parser().parse_args()
    configure_django()
    ensure_safe_database()

    if args.command == "prepare":
        result = prepare_fixture(args.requests, args.output)
    else:
        result = verify_fixture(args.fixture, args.output)

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
