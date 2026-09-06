from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('cases.urls', namespace='cases')),
    path('users/', include('users.urls', namespace='users')),
    path('inventory/', include('inventory.urls', namespace='inventory')),
    path('deposit/', include('payments.urls', namespace='payments')),
    path('upgrade/', include('upgrades.urls', namespace='upgrades')),
    path('contracts/', include('contracts.urls', namespace='contracts')),
    path('battles/', include('battles.urls', namespace='battles')),
    
    # Media file direct serving (uploaded case images, user avatars, etc.)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

handler400 = 'cases.views.custom_bad_request_view'
handler403 = 'cases.views.custom_permission_denied_view'
handler404 = 'cases.views.custom_page_not_found_view'
handler500 = 'cases.views.custom_server_error_view'

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
