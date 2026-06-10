from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0012_contactlead"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="age_verified",
            field=models.BooleanField(default=False),
        ),
    ]
