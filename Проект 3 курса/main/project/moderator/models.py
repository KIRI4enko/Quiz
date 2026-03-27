from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Moderator(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='moderator_profile')
    full_name = models.CharField(max_length=100, verbose_name="Полное имя")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name or self.user.username

    class Meta:
        verbose_name = "Модератор"
        verbose_name_plural = "Модераторы"

# Сигнал для автоматического создания профиля модератора при создании пользователя с is_staff=True
@receiver(post_save, sender=User)
def create_moderator_profile(sender, instance, created, **kwargs):
    if created and instance.is_staff:
        Moderator.objects.create(user=instance, full_name=instance.get_full_name() or instance.username)