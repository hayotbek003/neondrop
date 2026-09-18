from django.urls import path
from . import views
from . import views_uzum

app_name = 'payments'

urlpatterns = [
    path('', views.deposit_view, name='deposit'),
    path('api/create-request/', views.create_deposit_request_api, name='create_request'),
    path('api/create-withdrawal/', views.create_withdrawal_request_api, name='create_withdrawal'),
    
    # Uzum Checkout Acquiring Endpoints
    path('uzum/create-payment/', views_uzum.create_uzum_payment_api, name='uzum_create_payment'),
    path('uzum/webhook/', views_uzum.uzum_webhook, name='uzum_webhook'),
    path('uzum/return/', views_uzum.uzum_return_view, name='uzum_return'),
    path('uzum/status/', views_uzum.uzum_status_api, name='uzum_status'),
    path('uzum/simulate-sandbox-webhook/', views_uzum.simulate_sandbox_webhook_api, name='uzum_simulate_sandbox'),
]

