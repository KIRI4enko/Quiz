from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quiz", "0005_questionimage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="choice",
            name="text",
            field=models.CharField(blank=True, max_length=255, verbose_name="Текст варианта"),
        ),
        migrations.RemoveField(
            model_name="choice",
            name="order",
        ),
        migrations.RemoveField(
            model_name="questionimage",
            name="order",
        ),
    ]
