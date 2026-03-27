from django.contrib import admin
from django.urls import path, include
from . import views

'''
quiz...
'''

app_name = 'quiz'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('game/', views.GameView.as_view(), name='game'),
    path('logout/', views.TeamLogoutView.as_view(), name='logout'),
]