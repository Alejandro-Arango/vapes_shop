"""
Archivo: setup_admin_mfa.py
Descripcion: Aprovisiona y confirma TOTP para usuarios administrativos.
Dependencias: Django auth y django-otp
"""

from base64 import b32encode

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice


DEVICE_NAME = "Autenticador principal"
RECOVERY_DEVICE_NAME = "Codigos de recuperacion"
RECOVERY_CODE_COUNT = 10


class Command(BaseCommand):
    help = "Crea y confirma MFA TOTP para una cuenta administrativa."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--token",
            help="Codigo actual del autenticador para confirmar el dispositivo.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Reemplaza el dispositivo TOTP existente por uno nuevo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        user = self.get_admin_user(options["username"])
        token = str(options.get("token") or "").strip()
        replace = options["replace"]
        device = TOTPDevice.objects.filter(
            user=user,
            name=DEVICE_NAME,
        ).first()

        if replace:
            if token:
                raise CommandError(
                    "--replace y --token deben ejecutarse en pasos separados."
                )

            if device:
                device.delete()

            StaticDevice.objects.filter(
                user=user,
                name=RECOVERY_DEVICE_NAME,
            ).delete()
            device = None

        if device is None:
            device = TOTPDevice.objects.create(
                user=user,
                name=DEVICE_NAME,
                confirmed=False,
            )

        if token:
            self.confirm_device(device, token)
            return

        if device.confirmed:
            self.stdout.write(
                self.style.SUCCESS(
                    f"MFA ya esta configurado para {user.get_username()}."
                )
            )
            return

        secret = b32encode(device.bin_key).decode("ascii")

        self.stdout.write("Dispositivo TOTP pendiente creado.")
        self.stdout.write(f"Usuario: {user.get_username()}")
        self.stdout.write(f"Clave manual: {secret}")
        self.stdout.write(f"URI de configuracion: {device.config_url}")
        self.stdout.write(
            "Despues de agregarlo al autenticador, confirma con:"
        )
        self.stdout.write(
            f"python manage.py setup_admin_mfa {user.get_username()} --token CODIGO"
        )

    def get_admin_user(self, username):
        User = get_user_model()

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError("El usuario indicado no existe.") from exc

        if not user.is_active or not user.is_staff:
            raise CommandError(
                "El usuario debe estar activo y tener acceso administrativo."
            )

        return user

    def confirm_device(self, device, token):
        if device.confirmed:
            raise CommandError("El dispositivo TOTP ya esta confirmado.")

        if not device.verify_token(token):
            raise CommandError(
                "El codigo TOTP no es valido. Verifica la hora del dispositivo."
            )

        device.confirmed = True
        device.save(update_fields=["confirmed"])
        recovery_device, _ = StaticDevice.objects.get_or_create(
            user=device.user,
            name=RECOVERY_DEVICE_NAME,
            defaults={"confirmed": True},
        )

        if not recovery_device.confirmed:
            recovery_device.confirmed = True
            recovery_device.save(update_fields=["confirmed"])

        recovery_device.token_set.all().delete()
        recovery_codes = [
            StaticToken.random_token()
            for _ in range(RECOVERY_CODE_COUNT)
        ]
        StaticToken.objects.bulk_create(
            [
                StaticToken(device=recovery_device, token=code)
                for code in recovery_codes
            ]
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"MFA confirmado para {device.user.get_username()}."
            )
        )
        self.stdout.write(
            "Guarda estos codigos de recuperacion fuera del servidor:"
        )

        for code in recovery_codes:
            self.stdout.write(code)
