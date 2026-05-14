import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quiz", "0004_team_logo"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuestionImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="questions/gallery/", verbose_name="Файл")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gallery_images",
                        to="quiz.question",
                        verbose_name="Вопрос",
                    ),
                ),
            ],
            options={
                "verbose_name": "Изображение вопроса",
                "verbose_name_plural": "Изображения вопроса",
                "ordering": ["order", "id"],
            },
        ),
    ]
