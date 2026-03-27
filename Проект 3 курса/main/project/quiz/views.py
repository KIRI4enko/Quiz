from django.shortcuts import render, redirect
from django.views import View
from django.contrib import messages
from .models import Team, GameSession, TeamSession



class IndexView(View):
    """Главная страница: вход для команд"""
    def get(self, request):
        # Если команда уже в сессии, перенаправляем на страницу игры
        if 'team_id' in request.session:
            return redirect('quiz:game')
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
        
        # Перенаправляем на страницу игры
        return redirect('quiz:game')


class TeamLogoutView(View):
    """Выход команды"""
    def get(self, request):
        if 'team_id' in request.session:
            del request.session['team_id']
            del request.session['team_name']
        return redirect('quiz:index')


class GameView(View):
    def get(self, request):
        if 'team_id' not in request.session:
            return redirect('quiz:index')
        
        team = Team.objects.get(id=request.session['team_id'])
        
        # Ищем сессию, доступную для игры (активную или в подготовке)
        session = GameSession.objects.filter(status__in=['prep', 'active']).last()
        
        if not session:
            return render(request, 'quiz/game.html', {
                'team': team,
                'error': 'Нет активной игровой сессии. Дождитесь начала игры.'
            })
        
        # Создаём TeamSession, если ещё нет
        TeamSession.objects.get_or_create(team=team, game_session=session)
        
        context = {
            'team': team,
            'session': session,
        }
        return render(request, 'quiz/game.html', context)