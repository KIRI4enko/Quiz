from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Moderator

class ModeratorInline(admin.StackedInline):
    model = Moderator
    can_delete = False
    verbose_name_plural = "Профиль модератора"

class UserAdmin(BaseUserAdmin):
    inlines = [ModeratorInline]

# Перерегистрируем модель User с новым админом
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(Moderator)
class ModeratorAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'phone', 'created_at')
    search_fields = ('full_name', 'user__username')