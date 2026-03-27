from django.urls import path
from . import views

app_name = 'moderator'

urlpatterns = [
    # Панель управления (главная)
    path('', views.ModeratorPanelView.as_view(), name='panel'),
    path('login/', views.ModeratorLoginView.as_view(), name='login'),
    path('logout/', views.ModeratorLogoutView.as_view(), name='logout'),

    # Управление вопросами
    path('questions/', views.QuestionListView.as_view(), name='question_list'),
    path('questions/create/', views.QuestionCreateView.as_view(), name='question_create'),
    path('questions/<int:pk>/edit/', views.QuestionUpdateView.as_view(), name='question_edit'),
    path('questions/<int:pk>/delete/', views.QuestionDeleteView.as_view(), name='question_delete'),

    # Управление командами
    path('teams/', views.TeamListView.as_view(), name='team_list'),
    path('teams/create/', views.TeamCreateView.as_view(), name='team_create'),
    path('teams/<int:pk>/edit/', views.TeamUpdateView.as_view(), name='team_edit'),
    path('teams/<int:pk>/delete/', views.TeamDeleteView.as_view(), name='team_delete'),

    # Управление игровыми сессиями
    path('sessions/', views.GameSessionListView.as_view(), name='gamesession_list'),
    path('sessions/create/', views.GameSessionCreateView.as_view(), name='gamesession_create'),
    path('sessions/<int:pk>/', views.GameSessionDetailView.as_view(), name='gamesession_detail'),
    path('sessions/<int:pk>/add_question/', views.AddQuestionToSessionView.as_view(), name='add_question_to_session'),
    path('sessions/<int:pk>/remove_question/<int:gq_pk>/', views.RemoveQuestionFromSessionView.as_view(), name='remove_question_from_session'),
    path('sessions/<int:pk>/start/', views.StartGameSessionView.as_view(), name='start_game_session'),
    path('sessions/<int:pk>/end/', views.EndGameSessionView.as_view(), name='end_game_session'),

    path('sessions/<int:pk>/start_question/', views.StartQuestionView.as_view(), name='start_question'),
    path('sessions/<int:pk>/end_question_early/', views.EndQuestionEarlyView.as_view(), name='end_question_early'),
    path('sessions/<int:pk>/show_correct_answer/', views.ShowCorrectAnswerView.as_view(), name='show_correct_answer'),
]