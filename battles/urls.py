from django.urls import path
from . import views

app_name = 'battles'

urlpatterns = [
    path('', views.battles_view, name='index'),
    path('<int:battle_id>/', views.battle_detail_view, name='detail'),
    path('api/create/', views.create_battle_api, name='create'),
    path('api/join/<int:battle_id>/', views.join_battle_api, name='join'),
]
