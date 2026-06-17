"""
Archivo: setup_store_roles.py
Descripcion: Comando operativo para crear grupos y permisos administrativos base.
Dependencias: Django auth, contenttypes, BaseCommand, auditoria y modelos de store
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from store.audit import log_event
from store.models import (
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
    StockMovement,
)


ROLE_DEFINITIONS = {
    "Operador pedidos": (
        (Order, ("view", "change")),
        (OrderItem, ("view",)),
        (OrderStatusHistory, ("view", "add")),
        (Customer, ("view", "change")),
        (ShippingAddress, ("view",)),
        (Product, ("view",)),
        (DiscountCode, ("view",)),
    ),
    "Gestor inventario": (
        (Category, ("view", "add", "change")),
        (Product, ("view", "add", "change")),
        (StockMovement, ("view",)),
        (DiscountCode, ("view", "add", "change")),
        (Order, ("view",)),
        (OrderItem, ("view",)),
    ),
    "Atencion al cliente": (
        (ContactLead, ("view", "change")),
        (Customer, ("view",)),
        (ShippingAddress, ("view",)),
        (Order, ("view",)),
        (OrderItem, ("view",)),
        (ProductReview, ("view", "change")),
    ),
    "Auditor tienda": (
        (Category, ("view",)),
        (Product, ("view",)),
        (DiscountCode, ("view",)),
        (ContactLead, ("view",)),
        (Customer, ("view",)),
        (ShippingAddress, ("view",)),
        (Order, ("view",)),
        (OrderItem, ("view",)),
        (OrderStatusHistory, ("view",)),
        (ProductReview, ("view",)),
        (FavoriteProduct, ("view",)),
        (EventLog, ("view",)),
        (StockMovement, ("view",)),
    ),
}


def build_permission_codename(model, action):
    """
    Nombre: build_permission_codename
    Descripcion: Construye el codename estandar de permisos Django.
    """
    return f"{action}_{model._meta.model_name}"


def collect_role_permissions(role_models):
    """
    Nombre: collect_role_permissions
    Descripcion: Obtiene los permisos existentes para una definicion de rol.
    Retorna: Permisos encontrados y codenames faltantes.
    """
    permissions = []
    missing_permissions = []

    for model, actions in role_models:
        content_type = ContentType.objects.get_for_model(model)
        codenames = [
            build_permission_codename(model, action)
            for action in actions
        ]
        found_permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type=content_type,
                codename__in=codenames,
            )
        }

        for codename in codenames:
            permission = found_permissions.get(codename)

            if permission:
                permissions.append(permission)
            else:
                missing_permissions.append(f"{model._meta.label_lower}.{codename}")

    unique_permissions = {
        permission.pk: permission
        for permission in permissions
    }

    return list(unique_permissions.values()), missing_permissions


class Command(BaseCommand):
    """
    Nombre: Command
    Descripcion: Prepara grupos administrativos sin otorgar permisos destructivos.
    """

    help = "Crea o actualiza grupos administrativos base para la tienda."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Crea o actualiza los grupos. Sin esta opcion solo simula.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        planned_roles = []
        total_permissions = 0
        assigned_permissions = 0
        created_groups = 0

        for role_name, role_models in ROLE_DEFINITIONS.items():
            permissions, missing_permissions = collect_role_permissions(role_models)

            if missing_permissions:
                raise CommandError(
                    "No se encontraron permisos requeridos: "
                    + ", ".join(missing_permissions)
                )

            planned_roles.append((role_name, permissions))
            total_permissions += len(permissions)

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    "Simulacion: usa --apply para crear o actualizar los grupos."
                )
            )

            for role_name, permissions in planned_roles:
                self.stdout.write(f"- {role_name}: {len(permissions)} permiso(s).")

            return

        for role_name, permissions in planned_roles:
            group, created = Group.objects.get_or_create(name=role_name)
            current_permission_ids = set(
                group.permissions.values_list("id", flat=True)
            )
            new_permissions = [
                permission
                for permission in permissions
                if permission.id not in current_permission_ids
            ]

            if created:
                created_groups += 1

            if new_permissions:
                group.permissions.add(*new_permissions)
                assigned_permissions += len(new_permissions)

            self.stdout.write(
                f"- {role_name}: {len(new_permissions)} permiso(s) agregado(s)."
            )

        log_event(
            "store_roles_setup_completed",
            "Roles administrativos base actualizados.",
            severity="info",
            metadata={
                "role_count": len(planned_roles),
                "created_groups": created_groups,
                "assigned_permissions": assigned_permissions,
                "planned_permissions": total_permissions,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Roles administrativos actualizados: "
                f"{created_groups} grupo(s) creado(s), "
                f"{assigned_permissions} permiso(s) asignado(s)."
            )
        )
