from django.urls import path
from . import views

app_name = 'upgrades'

urlpatterns = [
    path('', views.upgrade_view, name='index'),
    path('api/calculate/', views.calculate_chance_api, name='calculate_chance'),
    path('api/execute/', views.execute_upgrade_api, name='execute'),
]
