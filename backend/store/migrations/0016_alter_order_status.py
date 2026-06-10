from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0015_eventlog"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pendiente", "Pendiente"),
                    ("pagado", "Pagado"),
                    ("en_preparacion", "En preparacion"),
                    ("enviado", "Enviado"),
                    ("entregado", "Entregado"),
                    ("cancelado", "Cancelado"),
                    ("reembolsado", "Reembolsado"),
                ],
                default="pendiente",
                max_length=20,
            ),
        ),
    ]
