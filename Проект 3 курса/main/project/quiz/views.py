from django.shortcuts import render, redirect
from django.views import View
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from .models import Team, GameSession, TeamSession



class IndexView(View):
    """Главная страница: вход для команд"""
    def get(self, request):
        # Если команда уже авторизована, отправляем к выбору комнаты / в игру
        if 'team_id' in request.session:
            if 'game_session_id' in request.session:
                return redirect('quiz:game')
            return redirect('quiz:gamesession_list')
        return render(request, 'quiz/index.html')

    def post(self, request):
        team_name = request.POST.get('team_name')
        password = request.POST.get('password')
        
        try:
            team = Team.objects.get(name=team_name, password=password)
        except Team.DoesNotExist:
            messages.error(request, 'Неверное название команды или пароль')
            return redirect('quiz:index')
        
        # Сохраняем ID команды в сессии
        request.session['team_id'] = team.id
        request.session['team_name'] = team.name
        request.session.pop('game_session_id', None)
        
        # После входа команда выбирает комнату вручную
        return redirect('quiz:gamesession_list')


class GameSessionListView(View):
    """Список комнат, доступных для входа командам"""
    def get(self, request):
        if 'team_id' not in request.session:
            return redirect('quiz:index')

        sessions = GameSession.objects.filter(status__in=['prep', 'active']).order_by('-created_at')
        return render(request, 'gamesession_list.html', {'sessions': sessions})


class JoinGameSessionView(View):
    """Присоединение команды к выбранной игровой сессии"""
    def post(self, request, pk):
        if 'team_id' not in request.session:
            return redirect('quiz:index')

        team = Team.objects.get(id=request.session['team_id'])
        session = GameSession.objects.filter(pk=pk, status__in=['prep', 'active']).first()

        if not session:
            messages.error(request, 'Эта сессия недоступна для подключения.')
            return redirect('quiz:gamesession_list')

        TeamSession.objects.get_or_create(team=team, game_session=session)
        request.session['game_session_id'] = session.id
        return redirect('quiz:game')


class TeamLogoutView(View):
    """Выход команды"""
    def get(self, request):
        if 'team_id' in request.session:
            del request.session['team_id']
            del request.session['team_name']
        request.session.pop('game_session_id', None)
        return redirect('quiz:index')


class GameView(View):
    def get(self, request):
        if 'team_id' not in request.session:
            return redirect('quiz:index')
        
        team = Team.objects.get(id=request.session['team_id'])

        session_id = request.session.get('game_session_id')
        session = None
        if session_id:
            session = GameSession.objects.filter(id=session_id, status__in=['prep', 'active']).first()

        if not session:
            messages.info(request, 'Выберите игровую сессию для входа в комнату.')
            return redirect('quiz:gamesession_list')

        # Создаём TeamSession, если ещё нет
        TeamSession.objects.get_or_create(team=team, game_session=session)
        
        context = {
            'team': team,
            'session': session,
            'is_moderator': False,
        }
        return render(request, 'quiz/game.html', context)


class ModeratorGameView(View):
    """Страница игры для модератора (наблюдение + кнопки управления)"""
    def get(self, request, pk):
        if not request.user.is_authenticated or not hasattr(request.user, 'moderator_profile'):
            raise PermissionDenied("У вас нет прав модератора.")

        session = GameSession.objects.filter(id=pk).first()
        if not session:
            messages.error(request, 'Игровая сессия не найдена.')
            return redirect('moderator:panel')

        context = {
            'team': None,
            'session': session,
            'is_moderator': True,
            'moderator_name': request.user.username,
        }
        return render(request, 'quiz/game.html', context)