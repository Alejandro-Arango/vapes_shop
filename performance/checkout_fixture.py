#!/usr/bin/env python3
"""
Prepara sesiones efimeras y verifica invariantes del checkout concurrente.
Solo opera cuando la base de datos esta marcada explicitamente para rendimiento.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4


USER_PREFIX = "load-checkout-"
CATEGORY_NAME = "Carga checkout"
PRODUCT_NAME = "Producto checkout concurrente"


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


def prepare_fixture(buyer_count, available_stock, output_path):
    from django.conf import settings
    from django.contrib.auth.models import User
    from django.test import Client

    from store.models import Category, Product

    if buyer_count < 2:
        raise RuntimeError("buyer_count debe ser al menos 2.")

    if available_stock < 1 or available_stock >= buyer_count:
        raise RuntimeError(
            "available_stock debe ser positivo y menor que buyer_count."
        )

    if User.objects.filter(username__startswith=USER_PREFIX).exists():
        raise RuntimeError("La base ya contiene usuarios de carga.")

    if Category.objects.filter(name=CATEGORY_NAME).exists():
        raise RuntimeError("La base ya contiene la categoria de carga.")

    category = Category.objects.create(
        name=CATEGORY_NAME,
        description="Datos efimeros para validar concurrencia.",
    )
    product = Product.objects.create(
        name=PRODUCT_NAME,
        category=category,
        description="Producto efimero con inventario limitado.",
        price="25.00",
        stock=available_stock,
    )
    run_id = str(uuid4())
    buyers = []

    for index in range(1, buyer_count + 1):
        user = User.objects.create_user(
            username=f"{USER_PREFIX}{index:03d}",
            email=f"{USER_PREFIX}{index:03d}@example.invalid",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        session = client.session
        session["cart"] = {str(product.id): 1}
        session.save()

        response = client.get("/", HTTP_HOST="localhost")

        if response.status_code != 200:
            raise RuntimeError(
                f"No fue posible obtener CSRF para {user.username}."
            )

        session_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
        csrf_cookie = client.cookies.get(settings.CSRF_COOKIE_NAME)

        if session_cookie is None or csrf_cookie is None:
            raise RuntimeError(
                f"No se generaron cookies para {user.username}."
            )

        buyers.append(
            {
                "csrf_token": csrf_cookie.value,
                "idempotency_key": str(uuid4()),
                "session_key": session_cookie.value,
                "username": user.username,
            }
        )

    fixture = {
        "available_stock": available_stock,
        "buyer_count": buyer_count,
        "buyers": buyers,
        "csrf_cookie_name": settings.CSRF_COOKIE_NAME,
        "product_id": product.id,
        "run_id": run_id,
        "session_cookie_name": settings.SESSION_COOKIE_NAME,
    }
    write_json(output_path, fixture)

    return {
        "available_stock": available_stock,
        "buyer_count": buyer_count,
        "product_id": product.id,
        "run_id": run_id,
    }


def build_verification(fixture):
    from django.db.models import Sum

    from store.models import (
        EventLog,
        Order,
        OrderItem,
        OrderStatusHistory,
        Product,
        StockMovement,
    )

    tokens = [
        UUID(buyer["idempotency_key"])
        for buyer in fixture["buyers"]
    ]
    expected_successes = int(fixture["available_stock"])
    expected_rejections = int(fixture["buyer_count"]) - expected_successes
    orders = Order.objects.filter(checkout_token__in=tokens)
    order_items = OrderItem.objects.filter(order__in=orders)
    movements = StockMovement.objects.filter(
        order__in=orders,
        movement_type="checkout",
    )
    histories = OrderStatusHistory.objects.filter(order__in=orders)
    product = Product.objects.get(id=fixture["product_id"])
    order_count = orders.count()
    item_count = order_items.count()
    item_quantity = order_items.aggregate(total=Sum("quantity"))["total"] or 0
    movement_count = movements.count()
    movement_quantity = movements.aggregate(total=Sum("quantity"))["total"] or 0
    success_events = EventLog.objects.filter(
        event_type="checkout_success"
    ).count()
    replay_events = EventLog.objects.filter(
        event_type="checkout_idempotent_replay"
    ).count()
    failed_events = EventLog.objects.filter(
        event_type="checkout_failed"
    ).count()
    invalid_orders = orders.exclude(
        status="pagado",
        completed=True,
        age_verified=True,
    ).count()

    checks = {
        "failed_events_match_rejections": (
            failed_events == expected_rejections
        ),
        "history_count_matches_orders": histories.count() == expected_successes,
        "idempotency_replays_match_orders": (
            replay_events == expected_successes
        ),
        "item_quantity_matches_stock": item_quantity == expected_successes,
        "movement_count_matches_orders": (
            movement_count == expected_successes
        ),
        "movement_quantity_matches_stock": (
            movement_quantity == -expected_successes
        ),
        "one_item_per_order": item_count == expected_successes,
        "order_count_matches_initial_stock": (
            order_count == expected_successes
        ),
        "orders_have_valid_state": invalid_orders == 0,
        "product_stock_is_zero": product.stock == 0,
        "success_events_match_orders": success_events == expected_successes,
    }
    return {
        "checks": checks,
        "details": {
            "expected_rejections": expected_rejections,
            "expected_successes": expected_successes,
            "failed_events": failed_events,
            "final_stock": product.stock,
            "item_count": item_count,
            "item_quantity": item_quantity,
            "movement_count": movement_count,
            "movement_quantity": movement_quantity,
            "order_count": order_count,
            "replay_events": replay_events,
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
    prepare.add_argument("--buyers", type=int, required=True)
    prepare.add_argument("--stock", type=int, required=True)
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
        result = prepare_fixture(args.buyers, args.stock, args.output)
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
