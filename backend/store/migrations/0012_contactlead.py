from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0011_order_shipping_address_order_shipping_city_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContactLead",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email", models.EmailField(max_length=254)),
                ("whatsapp_message", models.TextField(blank=True)),
                ("email_notification_sent", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
    ]
