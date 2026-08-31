from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('', views.deposit_view, name='deposit'),
    path('api/create-request/', views.create_deposit_request_api, name='create_request'),
]
