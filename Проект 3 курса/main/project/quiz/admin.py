from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Answer,
    Choice,
    GameQuestion,
    GameSession,
    Question,
    QuestionImage,
    Team,
    TeamSession,
)


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0


class QuestionImageInline(admin.TabularInline):
    model = QuestionImage
    extra = 1
    fields = ("image", "preview")

    readonly_fields = ("preview",)

    @admin.display(description="Предпросмотр")
    def preview(self, obj):
        if obj.pk and obj.image:
            return format_html(
                '<img src="{}" alt="" style="max-height:72px;border-radius:8px;" />',
                obj.image.url,
            )
        return "—"


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "thumb", "text_short", "time_limit", "created_at")
    list_display_links = ("id", "text_short")
    search_fields = ("text",)
    inlines = [QuestionImageInline, ChoiceInline]

    @admin.display(description="")
    def thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" alt="" class="quiz-admin-thumb" />',
                obj.image.url,
            )
        first = obj.gallery_images.first()
        if first and first.image:
            return format_html(
                '<img src="{}" alt="" class="quiz-admin-thumb" />',
                first.image.url,
            )
        return "—"

    @admin.display(description="Текст")
    def text_short(self, obj):
        t = (obj.text or "")[:80]
        return t + ("…" if len(obj.text or "") > 80 else "")


@admin.register(QuestionImage)
class QuestionImageAdmin(admin.ModelAdmin):
    list_display = ("id", "preview", "question")
    list_filter = ("question",)
    search_fields = ("question__text",)

    @admin.display(description="")
    def preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" alt="" style="max-height:64px;border-radius:8px;" />',
                obj.image.url,
            )
        return "—"


class GameQuestionInline(admin.TabularInline):
    model = GameQuestion
    extra = 0
    autocomplete_fields = ("question",)


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "created_at")
    list_filter = ("status",)
    inlines = [GameQuestionInline]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "logo_thumb", "created_at")
    search_fields = ("name",)

    @admin.display(description="Лого")
    def logo_thumb(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" alt="" style="max-height:40px;border-radius:6px;" />',
                obj.logo.url,
            )
        return "—"


@admin.register(TeamSession)
class TeamSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "game_session", "joined_at")


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "team_session", "game_question", "is_correct", "answered_at")
