from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView, View
from django.core.exceptions import PermissionDenied

from django.views.generic.edit import FormView
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme

from quiz.models import Question, Choice, Team, GameSession, GameQuestion, TeamSession, QuestionImage
from .forms import QuestionForm, ChoiceFormSet, TeamForm, GameSessionForm
from django.db import models
from django.utils import timezone

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from quiz.image_payload import question_image_urls_for_request

from django.core.paginator import Paginator
from django.views import View


GALLERY_MAX_SLOTS = 4


def _save_gallery_from_post(request, question):
    for i in range(GALLERY_MAX_SLOTS):
        pk = request.POST.get(f"gallery_pk_{i}")
        f = request.FILES.get(f"gallery_{i}")
        delete = request.POST.get(f"gallery_delete_{i}") == "1"
        if pk:
            try:
                img = QuestionImage.objects.get(pk=int(pk), question_id=question.id)
            except (QuestionImage.DoesNotExist, ValueError):
                continue
            if delete:
                img.delete()
            elif f:
                img.image = f
                img.save()
        elif f:
            if question.gallery_images.count() < GALLERY_MAX_SLOTS:
                QuestionImage.objects.create(question=question, image=f)


def _apply_correct_choice_slot(request, choice_formset):
    slot = request.POST.get("correct_answer_slot")
    if slot not in ("0", "1", "2", "3"):
        return "Выберите правильный ответ (одна из позиций 1–4)."
    ci = int(slot)
    form_at = choice_formset.forms[ci]
    if not form_at.cleaned_data or not (form_at.cleaned_data.get("text") or "").strip():
        return "Правильным может быть только вариант с непустым текстом."
    return None


def _finalize_correct_choice_after_save(question, choice_formset, correct_slot_index):
    correct_pk = choice_formset.forms[correct_slot_index].instance.pk
    _purge_empty_choices(question)
    Choice.objects.filter(question=question).update(is_correct=False)
    if correct_pk and Choice.objects.filter(pk=correct_pk, question_id=question.id).exists():
        Choice.objects.filter(pk=correct_pk).update(is_correct=True)


def _purge_empty_choices(question):
    for c in list(question.choices.all()):
        if not (c.text or "").strip():
            c.delete()


def redirect_back_or_session(request, pk):
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('moderator:gamesession_detail', pk=pk)

# Миксин для проверки, что пользователь является модератором (имеет профиль)
class ModeratorRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        # Проверяем наличие профиля модератора
        if not hasattr(request.user, 'moderator_profile'):
            raise PermissionDenied("У вас нет прав модератора.")
        return super().dispatch(request, *args, **kwargs)

# Вход для модераторов
class ModeratorLoginView(LoginView):
    template_name = 'moderator/login.html'
    next_page = reverse_lazy('moderator:panel')  # после входа переходим в панель

    def get_success_url(self):
        # Дополнительная проверка, что вошедший пользователь - модератор
        if not hasattr(self.request.user, 'moderator_profile'):
            # Если нет профиля, выходим и перенаправляем на страницу входа с ошибкой
            from django.contrib.auth import logout
            logout(self.request)
            return reverse_lazy('moderator:login')
        return super().get_success_url()

# Панель модератора
class ModeratorPanelView(ModeratorRequiredMixin, TemplateView):
    template_name = 'moderator/panel.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Добавляем данные профиля модератора в контекст
        context['moderator'] = self.request.user.moderator_profile
        return context

# Выход
class ModeratorLogoutView(LogoutView):
    next_page = '/'  # после выхода на главную


# Миксин проверки модератора (уже есть, но продублируем для целостности)
class ModeratorRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not hasattr(request.user, 'moderator_profile'):
            raise PermissionDenied("У вас нет прав модератора.")
        return super().dispatch(request, *args, **kwargs)


# ========== Управление вопросами ==========

class QuestionListView(ModeratorRequiredMixin, ListView):
    model = Question
    template_name = 'moderator/question_list.html'
    context_object_name = 'questions'
    paginate_by = 10

    def get_queryset(self):
        return Question.objects.prefetch_related('gallery_images').order_by('-created_at')


class QuestionCreateView(ModeratorRequiredMixin, CreateView):
    model = Question
    form_class = QuestionForm
    template_name = 'moderator/question_form.html'
    success_url = reverse_lazy('moderator:question_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['choice_formset'] = ChoiceFormSet(self.request.POST)
        else:
            data['choice_formset'] = ChoiceFormSet()
        
        # Для нового вопроса изображений нет, но создаём 4 пустых слота
        gallery_slots = [{'index': i, 'obj': None} for i in range(4)]
        data['gallery_slots'] = gallery_slots
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        choice_formset = context['choice_formset']
        if not choice_formset.is_valid():
            return self.form_invalid(form)
        err = _apply_correct_choice_slot(self.request, choice_formset)
        if err:
            messages.error(self.request, err)
            return self.form_invalid(form)
        self.object = form.save()
        choice_formset.instance = self.object
        choice_formset.save()
        _save_gallery_from_post(self.request, self.object)
        _finalize_correct_choice_after_save(
            self.object, choice_formset, int(self.request.POST.get('correct_answer_slot'))
        )
        if not self.object.choices.filter(is_correct=True).exists():
            messages.warning(self.request, 'Не удалось отметить правильный ответ. Проверьте форму.')
        return HttpResponseRedirect(self.get_success_url())


class QuestionUpdateView(ModeratorRequiredMixin, UpdateView):
    model = Question
    form_class = QuestionForm
    template_name = 'moderator/question_form.html'
    success_url = reverse_lazy('moderator:question_list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        
        # Обработка формсета вариантов ответа
        if self.request.POST:
            data['choice_formset'] = ChoiceFormSet(self.request.POST, instance=self.object)
        else:
            data['choice_formset'] = ChoiceFormSet(instance=self.object)
        
        # ---- Генерация 4 слотов для изображений ----
        existing_images = list(self.object.gallery_images.all())  # используем related_name 'gallery_images'
        gallery_slots = []
        for i in range(4):
            if i < len(existing_images):
                gallery_slots.append({
                    'index': i,
                    'obj': existing_images[i],
                })
            else:
                gallery_slots.append({
                    'index': i,
                    'obj': None,
                })
        data['gallery_slots'] = gallery_slots  
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        choice_formset = context['choice_formset']
        if not choice_formset.is_valid():
            return self.form_invalid(form)
        err = _apply_correct_choice_slot(self.request, choice_formset)
        if err:
            messages.error(self.request, err)
            return self.form_invalid(form)
        self.object = form.save()
        choice_formset.instance = self.object
        choice_formset.save()
        _save_gallery_from_post(self.request, self.object)
        _finalize_correct_choice_after_save(
            self.object, choice_formset, int(self.request.POST.get('correct_answer_slot'))
        )
        if not self.object.choices.filter(is_correct=True).exists():
            messages.warning(self.request, 'Не удалось отметить правильный ответ. Проверьте форму.')
        return HttpResponseRedirect(self.get_success_url())

class QuestionDeleteView(ModeratorRequiredMixin, DeleteView):
    model = Question
    success_url = reverse_lazy('moderator:question_list')

    def post(self, request, pk):
        question = get_object_or_404(Question, pk=pk)
        question_name = str(question.text)
        question.delete()
        messages.success(request, f"Вопрос {question_name} удален.")
        return redirect('moderator:question_list')

# ========== Управление командами ==========

class TeamListView(ModeratorRequiredMixin, ListView):
    model = Team
    template_name = 'moderator/team_list.html'
    context_object_name = 'teams'
    paginate_by = 10
    ordering = ['name']


class TeamCreateView(ModeratorRequiredMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = 'moderator/team_form.html'
    success_url = reverse_lazy('moderator:team_list')


class TeamUpdateView(ModeratorRequiredMixin, UpdateView):
    model = Team
    form_class = TeamForm
    template_name = 'moderator/team_form.html'
    success_url = reverse_lazy('moderator:team_list')


class TeamDeleteView(ModeratorRequiredMixin, DeleteView):
    model = Team
    success_url = reverse_lazy('moderator:team_list')

    def post(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        name = str(team.name)
        team.delete()
        messages.success(request, f"Команда {name} удалена")
        return redirect("moderator:team_list")

# ========== Управление игровыми сессиями ==========

class GameSessionListView(ModeratorRequiredMixin, ListView):
    model = GameSession
    template_name = 'moderator/gamesession_list.html'
    context_object_name = 'sessions'
    paginate_by = 10
    ordering = ['-created_at']


class GameSessionCreateView(ModeratorRequiredMixin, CreateView):
    model = GameSession
    form_class = GameSessionForm
    template_name = 'moderator/gamesession_form.html'
    success_url = reverse_lazy('moderator:gamesession_list')


class GameSessionDeleteView(ModeratorRequiredMixin, DeleteView):
    model = GameSession
    template_name = 'moderator/gamesession_confirm_delete.html'  # можно не использовать, если удаляешь прямо из списка
    success_url = reverse_lazy('moderator:gamesession_list')

    def post(self, request, pk):
        session = get_object_or_404(GameSession, pk=pk)
        name = str(session.name)
        session.delete()
        messages.success(request, f"Сессия {name} удалена.")
        return redirect('moderator:gamesession_list')


class GameSessionDetailView(ModeratorRequiredMixin, DetailView):
    model = GameSession
    template_name = 'moderator/gamesession_detail.html'
    context_object_name = 'session'

    def get_queryset(self):
        return GameSession.objects.select_related(
            "current_game_question__question",
        ).prefetch_related(
            "game_questions__question__gallery_images",
            "current_game_question__question__gallery_images",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Список всех вопросов для добавления в сессию
        context['available_questions'] = Question.objects.prefetch_related('gallery_images').all()
        # Вопросы, уже включённые в сессию
        context['game_questions'] = self.object.game_questions.all().order_by('order')
        return context

# Представление для добавления вопроса в сессию
class AddQuestionToSessionView(ModeratorRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(GameSession, pk=pk)
        question_id = request.POST.get('question_id')
        if not question_id:
            messages.error(request, "Не выбран вопрос.")
            return redirect('moderator:gamesession_detail', pk=pk)
        question = get_object_or_404(Question, pk=question_id)
        # Определяем следующий порядковый номер
        max_order = session.game_questions.aggregate(models.Max('order'))['order__max'] or 0
        GameQuestion.objects.create(
            game_session=session,
            question=question,
            order=max_order + 1
        )
        messages.success(request, f"Вопрос '{question}' добавлен в сессию.")
        return redirect('moderator:gamesession_detail', pk=pk)


# Представление для удаления вопроса из сессии
class RemoveQuestionFromSessionView(ModeratorRequiredMixin, View):
    def post(self, request, pk, gq_pk):
        game_question = get_object_or_404(GameQuestion, pk=gq_pk, game_session_id=pk)
        game_question.delete()
        messages.success(request, "Вопрос удалён из сессии.")
        return redirect('moderator:gamesession_detail', pk=pk)


# Представление для запуска игры (переход в активный режим)
class StartGameSessionView(ModeratorRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(GameSession, pk=pk)
        if session.status != 'prep':
            messages.error(request, "Игра уже запущена или завершена.")
            return redirect_back_or_session(request, pk)
        if not session.game_questions.exists():
            messages.error(request, "Нельзя запустить игру без вопросов.")
            return redirect_back_or_session(request, pk)
        session.status = 'active'
        session.start_time = timezone.now()
        session.save()
        messages.success(request, "Игра запущена!")
        # Здесь можно добавить логику рассылки через WebSocket, но пока просто редирект
        return redirect_back_or_session(request, pk)
    
class EndGameSessionView(ModeratorRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(GameSession, pk=pk)
        if session.status != 'active':
            messages.error(request, "Игра не активна.")
            return redirect_back_or_session(request, pk)
        session.status = 'finished'
        session.end_time = timezone.now()
        session.save()
        messages.success(request, "Игра завершена.")
        # Здесь можно отправить сигнал через WebSocket всем командам о завершении
        return redirect_back_or_session(request, pk)
    
class StartQuestionView(ModeratorRequiredMixin, View):
    """Запуск следующего вопроса в активной сессии"""
    def post(self, request, pk):
        session = get_object_or_404(GameSession, pk=pk)
        if session.status != 'active':
            messages.error(request, "Игра не активна.")
            return redirect_back_or_session(request, pk)
        
        # Находим следующий не начатый вопрос
        next_game_question = session.game_questions.filter(start_time__isnull=True).order_by('order').first()
        if not next_game_question:
            messages.error(request, "Нет больше вопросов.")
            return redirect_back_or_session(request, pk)
        
        # Устанавливаем время начала
        next_game_question.start_time = timezone.now()
        next_game_question.save()
        
        # Устанавливаем как текущий вопрос в сессии
        session.current_game_question = next_game_question
        session.save()
        
        # Отправляем уведомление через WebSocket
        channel_layer = get_channel_layer()
        question = next_game_question.question
        image_urls = question_image_urls_for_request(request, question)

        async_to_sync(channel_layer.group_send)(
            f'game_{session.id}',
            {
                'type': 'new_question',
                'game_question_id': next_game_question.id,
                'question_text': question.text,
                'image_urls': image_urls,
                'image_url': image_urls[0] if image_urls else None,
                'choices': [
                    {'id': c.id, 'text': c.text}
                    for c in question.choices.all().order_by('id')
                ],
                'time_limit': question.time_limit,
                'start_time': next_game_question.start_time.isoformat()
            }
        )
        
        messages.success(request, f"Вопрос {next_game_question.order} запущен.")
        return redirect_back_or_session(request, pk)


class EndQuestionEarlyView(ModeratorRequiredMixin, View):
    """Досрочно завершить текущий вопрос (принудительно остановить приём ответов)"""
    def post(self, request, pk):
        session = get_object_or_404(GameSession, pk=pk)
        if session.status != 'active' or not session.current_game_question:
            messages.error(request, "Нет активного вопроса.")
            return redirect_back_or_session(request, pk)
        
        current_gq = session.current_game_question
        
        # Можно просто снять флаг current_game_question, но вопрос останется начатым.
        # Лучше ничего не менять в БД, а просто отправить команду на клиенты о завершении вопроса.
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'game_{session.id}',
            {
                'type': 'game_message',
                'message': {
                    'type': 'question_ended',
                    'game_question_id': current_gq.id
                }
            }
        )
        
        # Очищаем текущий вопрос в сессии
        session.current_game_question = None
        session.save()
        
        messages.success(request, "Приём ответов остановлен.")
        return redirect_back_or_session(request, pk)


class ShowCorrectAnswerView(ModeratorRequiredMixin, View):
    """Показать командам правильный ответ (после завершения вопроса)"""
    def post(self, request, pk):
        session = get_object_or_404(GameSession, pk=pk)
        last_gq = session.game_questions.filter(start_time__isnull=False).order_by('-start_time').first()
        if not last_gq:
            messages.error(request, "Нет завершённых вопросов.")
            return redirect_back_or_session(request, pk)
        
        correct_choice = last_gq.question.choices.filter(is_correct=True).first()
        if not correct_choice:
            messages.error(request, "У вопроса нет правильного ответа.")
            return redirect_back_or_session(request, pk)
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'game_{session.id}',
            {
                'type': 'game_message',
                'message': {
                    'type': 'show_correct_answer',
                    'game_question_id': last_gq.id,
                    'correct_choice_id': correct_choice.id,
                    'correct_text': correct_choice.text
                }
            }
        )
        
        messages.success(request, "Правильный ответ показан.")
        return redirect_back_or_session(request, pk)
    


class SelectQuestionView(ModeratorRequiredMixin, View):
    """Страница выбора вопросов для добавления в сессию (карточки + пагинация)"""
    def get(self, request, pk):
        session = get_object_or_404(GameSession, pk=pk)
        if session.status != 'prep':
            messages.error(request, 'Вопросы можно добавлять только в сессию в статусе "Подготовка"')
            return redirect('moderator:gamesession_detail', pk=pk)
        
        # Список вопросов, которые ещё не добавлены в сессию
        existing_question_ids = session.game_questions.values_list('question_id', flat=True)
        questions = Question.objects.exclude(id__in=existing_question_ids).order_by('-created_at')
        
        paginator = Paginator(questions, 6)  # по 12 вопросов на страницу
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        context = {
            'session': session,
            'page_obj': page_obj,
        }
        return render(request, 'moderator/select_question.html', context)

    def post(self, request, pk):
        """Обработка добавления вопроса (через кнопку на карточке)"""
        session = get_object_or_404(GameSession, pk=pk)
        if session.status != 'prep':
            messages.error(request, 'Нельзя добавить вопрос в активную или завершённую сессию')
            return redirect('moderator:gamesession_detail', pk=pk)
        
        question_id = request.POST.get('question_id')
        if not question_id:
            messages.error(request, 'Не выбран вопрос')
            return redirect('moderator:select_question', pk=pk)
        
        question = get_object_or_404(Question, pk=question_id)
        # Проверяем, не добавлен ли уже
        if session.game_questions.filter(question_id=question_id).exists():
            messages.warning(request, 'Этот вопрос уже есть в сессии')
            return redirect('moderator:select_question', pk=pk)
        
        max_order = session.game_questions.aggregate(models.Max('order'))['order__max'] or 0
        from quiz.models import GameQuestion
        GameQuestion.objects.create(
            game_session=session,
            question=question,
            order=max_order + 1
        )
        messages.success(request, f'Вопрос "{question.text[:50]}" добавлен в сессию')
        return redirect('moderator:gamesession_detail', pk=pk)