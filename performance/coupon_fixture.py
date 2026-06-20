#!/usr/bin/env python3
"""
Prepara y verifica un limite global de cupon bajo checkouts concurrentes.
Cada comprador usa un producto distinto para aislar el bloqueo del cupon.
"""

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4


USER_PREFIX = "load-coupon-"
CATEGORY_NAME = "Carga cupon"
COUPON_CODE = "CONCURRENCIA"
COUPON_VALUE = Decimal("5.00")


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


def prepare_fixture(buyer_count, max_uses, output_path):
    from django.conf import settings
    from django.contrib.auth.models import User
    from django.test import Client

    from store.models import Category, DiscountCode, Product

    if buyer_count < 2:
        raise RuntimeError("buyer_count debe ser al menos 2.")

    if max_uses < 1 or max_uses >= buyer_count:
        raise RuntimeError(
            "max_uses debe ser positivo y menor que buyer_count."
        )

    if User.objects.filter(username__startswith=USER_PREFIX).exists():
        raise RuntimeError("La base ya contiene usuarios de cupon.")

    if DiscountCode.objects.filter(code=COUPON_CODE).exists():
        raise RuntimeError("La base ya contiene el cupon de carga.")

    category = Category.objects.create(
        name=CATEGORY_NAME,
        description="Datos efimeros para contencion de cupon.",
    )
    coupon = DiscountCode.objects.create(
        code=COUPON_CODE,
        description="Cupon efimero con limite global.",
        discount_type="fixed",
        value=COUPON_VALUE,
        max_uses=max_uses,
    )
    run_id = str(uuid4())
    buyers = []
    product_ids = []

    for index in range(1, buyer_count + 1):
        product = Product.objects.create(
            name=f"Producto cupon {index:03d}",
            category=category,
            description="Producto independiente para aislar el cupon.",
            price="25.00",
            stock=1,
        )
        product_ids.append(product.id)

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
        session["coupon_code"] = coupon.code
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
                "product_id": product.id,
                "session_key": session_cookie.value,
                "username": user.username,
            }
        )

    fixture = {
        "buyer_count": buyer_count,
        "buyers": buyers,
        "coupon_code": coupon.code,
        "coupon_id": coupon.id,
        "coupon_max_uses": max_uses,
        "coupon_value": str(COUPON_VALUE),
        "csrf_cookie_name": settings.CSRF_COOKIE_NAME,
        "product_ids": product_ids,
        "run_id": run_id,
        "session_cookie_name": settings.SESSION_COOKIE_NAME,
    }
    write_json(output_path, fixture)

    return {
        "buyer_count": buyer_count,
        "coupon_code": coupon.code,
        "max_uses": max_uses,
        "run_id": run_id,
    }


def count_events(event_type, order_ids):
    from store.models import EventLog

    return sum(
        EventLog.objects.filter(
            event_type=event_type,
            metadata__order_id=order_id,
        ).count()
        for order_id in order_ids
    )


def build_verification(fixture):
    from django.db.models import Sum

    from store.models import (
        DiscountCode,
        EventLog,
        Order,
        OrderItem,
        Product,
        StockMovement,
    )

    tokens = [
        UUID(buyer["idempotency_key"])
        for buyer in fixture["buyers"]
    ]
    expected_successes = int(fixture["coupon_max_uses"])
    expected_rejections = int(fixture["buyer_count"]) - expected_successes
    coupon_value = Decimal(fixture["coupon_value"])
    orders = Order.objects.filter(checkout_token__in=tokens)
    order_ids = list(orders.values_list("id", flat=True))
    order_items = OrderItem.objects.filter(order_id__in=order_ids)
    movements = StockMovement.objects.filter(
        order_id__in=order_ids,
        movement_type="checkout",
    )
    products = Product.objects.filter(id__in=fixture["product_ids"])
    coupon = DiscountCode.objects.get(id=fixture["coupon_id"])
    order_count = orders.count()
    discounted_orders = orders.filter(
        coupon_code=fixture["coupon_code"],
        discount_amount=coupon_value,
    ).count()
    total_discount = (
        orders.aggregate(total=Sum("discount_amount"))["total"]
        or Decimal("0.00")
    )
    remaining_stock = (
        products.aggregate(total=Sum("stock"))["total"]
        or 0
    )
    failed_events = EventLog.objects.filter(
        event_type="checkout_failed",
        metadata__coupon_code=fixture["coupon_code"],
    ).count()
    replay_events = count_events(
        "checkout_idempotent_replay",
        order_ids,
    )
    success_events = EventLog.objects.filter(
        event_type="checkout_success",
        metadata__coupon_code=fixture["coupon_code"],
    ).count()

    checks = {
        "coupon_usage_matches_limit": coupon.used_count == expected_successes,
        "discounted_orders_match_limit": (
            discounted_orders == expected_successes
        ),
        "failed_events_match_rejections": (
            failed_events == expected_rejections
        ),
        "idempotency_replays_match_orders": (
            replay_events == expected_successes
        ),
        "movement_count_matches_orders": (
            movements.count() == expected_successes
        ),
        "one_item_per_order": order_items.count() == expected_successes,
        "order_count_matches_coupon_limit": (
            order_count == expected_successes
        ),
        "remaining_stock_matches_rejections": (
            remaining_stock == expected_rejections
        ),
        "success_events_match_orders": success_events == expected_successes,
        "total_discount_matches_limit": (
            total_discount == coupon_value * expected_successes
        ),
    }
    return {
        "checks": checks,
        "details": {
            "coupon_used_count": coupon.used_count,
            "discounted_orders": discounted_orders,
            "expected_rejections": expected_rejections,
            "expected_successes": expected_successes,
            "failed_events": failed_events,
            "order_count": order_count,
            "remaining_stock": remaining_stock,
            "replay_events": replay_events,
            "success_events": success_events,
            "total_discount": str(total_discount),
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
    prepare.add_argument("--max-uses", type=int, required=True)
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
        result = prepare_fixture(
            args.buyers,
            args.max_uses,
            args.output,
        )
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
