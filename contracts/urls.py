from django.urls import path
from . import views

app_name = 'contracts'

urlpatterns = [
    path('', views.contracts_view, name='index'),
    path('api/create/', views.create_contract_api, name='create'),
]
