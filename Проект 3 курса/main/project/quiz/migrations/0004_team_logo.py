from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0003_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='logo',
            field=models.ImageField(blank=True, null=True, upload_to='teams/', verbose_name='Логотип'),
        ),
    ]
