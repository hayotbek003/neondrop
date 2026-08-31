from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.inventory_view, name='index'),
    path('sell/<int:item_id>/', views.sell_item_api, name='sell_item'),
    path('sell-all/', views.sell_all_api, name='sell_all'),
    path('api/list/', views.api_inventory_list, name='api_list'),
]
