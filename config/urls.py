from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

import cases.admin_views as admin_views
import cases.blogger_views as blogger_views
import users.admin_views as user_admin_views

urlpatterns = [
    # Dedicated Cyberpunk Admin Management System («👑 Управление администраторами»)
    path('admin/administrators/', user_admin_views.administrators_dashboard_view, name='admin_administrators'),
    path('admin/administrators/assign/', user_admin_views.assign_admin_view, name='admin_assign_administrator'),
    path('admin/administrators/<int:user_id>/update-perms/', user_admin_views.update_admin_perms_view, name='admin_update_perms'),
    path('admin/administrators/<int:user_id>/toggle-status/', user_admin_views.toggle_admin_status_view, name='admin_toggle_status'),
    path('admin/administrators/<int:user_id>/revoke/', user_admin_views.revoke_admin_view, name='admin_revoke_administrator'),

    # Dedicated Admin Backup / Restore GUI & Export Endpoints
    path('admin/backup-restore/', admin_views.admin_backup_restore_view, name='admin_backup_restore'),
    path('admin/backup-restore/download/', admin_views.admin_backup_download_view, name='admin_backup_download'),
    path('admin/backup-restore/export/users/', admin_views.export_users_csv_view, name='admin_export_users_csv'),
    path('admin/backup-restore/export/cases/', admin_views.export_cases_csv_view, name='admin_export_cases_csv'),
    path('admin/backup-restore/export/items/', admin_views.export_items_csv_view, name='admin_export_items_csv'),
    path('admin/backup-restore/export/case-contents/', admin_views.export_case_contents_csv_view, name='admin_export_case_contents_csv'),
    path('admin/backup-restore/export/openings/', admin_views.export_openings_csv_view, name='admin_export_openings_csv'),
    path('admin/backup-restore/export/transactions/', admin_views.export_transactions_csv_view, name='admin_export_transactions_csv'),

    # Dedicated Admin Blogger Statistics & Payout Management
    path('admin/bloggers/', blogger_views.blogger_dashboard_view, name='admin_blogger_dashboard'),
    path('admin/bloggers/payout/', blogger_views.mark_blogger_payout_view, name='admin_mark_blogger_payout'),
    path('admin/bloggers/export/', blogger_views.export_blogger_stats_csv_view, name='admin_export_blogger_stats_csv'),

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
