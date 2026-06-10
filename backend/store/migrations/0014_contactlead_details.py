from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0013_order_age_verified"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactlead",
            name="message",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="contactlead",
            name="name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="contactlead",
            name="phone",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="contactlead",
            name="status",
            field=models.CharField(
                choices=[
                    ("nuevo", "Nuevo"),
                    ("en_proceso", "En proceso"),
                    ("respondido", "Respondido"),
                    ("cerrado", "Cerrado"),
                ],
                default="nuevo",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="contactlead",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
