from django.contrib import admin
from django.urls import path, include
from . import views

'''
quiz...
'''

app_name = 'quiz'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('sessions/', views.GameSessionListView.as_view(), name='gamesession_list'),
    path('sessions/<int:pk>/join/', views.JoinGameSessionView.as_view(), name='join_gamesession'),
    path('game/', views.GameView.as_view(), name='game'),
    path('game/<int:pk>/moderator/', views.ModeratorGameView.as_view(), name='moderator_game'),
    path('logout/', views.TeamLogoutView.as_view(), name='logout'),
]