from django.urls import path
from . import views

app_name = 'cases'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('cases/', views.cases_list_view, name='cases_list'),
    path('cases/<slug:slug>/', views.case_detail_view, name='case_detail'),
    path('cases/<slug:slug>/open/', views.open_case_api, name='open_case_api'),
    path('api/cases/<slug:slug>/open/', views.open_case_api, name='api_open_case_slug'),
    path('api/cases/<int:case_id>/open/', views.open_case_by_id_api, name='api_open_case_id'),
    path('api/promocodes/redeem/', views.redeem_promocode_api, name='api_redeem_promocode'),
    path('promocodes/redeem/', views.redeem_promocode_api, name='redeem_promocode'),
    path('api/live-drops/', views.live_drops_api, name='live_drops_api'),
    path('top/', views.top_view, name='top'),
    path('fairness/', views.provably_fair_view, name='fairness'),
    path('api/verify-seed/', views.provably_fair_verify_api, name='verify_seed_api'),
]
