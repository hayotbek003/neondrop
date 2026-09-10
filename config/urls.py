from pathlib import Path
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.contrib.sitemaps.views import sitemap

import cases.admin_views as admin_views
import cases.blogger_views as blogger_views
import users.admin_views as user_admin_views
from cases.sitemaps import StaticViewSitemap, CaseSitemap
from cases.seo_views import robots_txt_view, google_verification_file_view, favicon_ico_view, webmanifest_view

sitemaps = {
    'static': StaticViewSitemap,
    'cases': CaseSitemap,
}

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

    # Dedicated Admin Image-Based Item Import & RTP Calculator
    path('admin/cases/image-import/', admin_views.admin_image_import_view, name='admin_image_import'),
    path('admin/cases/image-import/calculate-rtp/', admin_views.ajax_calculate_rtp_view, name='admin_ajax_calculate_rtp'),
    path('admin/cases/image-import/create-case/', admin_views.ajax_create_case_from_import_view, name='admin_ajax_create_case'),
    path('admin/cases/image-import/upload-grid/', admin_views.ajax_upload_grid_image_view, name='admin_ajax_upload_grid'),

    # Dedicated Admin PUBG ZIP Items Importer
    path('admin/cases/pubg-import/', admin_views.admin_pubg_import_view, name='admin_pubg_import'),
    path('admin/cases/pubg-import/stream/', admin_views.admin_pubg_import_stream_view, name='admin_pubg_import_stream'),
    path('admin/cases/pubg-import/thumb/<str:token>/<path:image_path>', admin_views.admin_pubg_import_thumb_view, name='admin_pubg_import_thumb'),

    # Dedicated Admin Provably Fair Server RNG Monte Carlo Simulator
    path('admin/cases/rng-simulation/', admin_views.admin_rng_simulation_view, name='admin_rng_simulation'),
    path('admin/cases/rng-simulation/run/', admin_views.ajax_run_rng_simulation_view, name='admin_ajax_run_rng_simulation'),
    path('admin/cases/rng-simulation/history/<int:run_id>/', admin_views.ajax_get_rng_simulation_run_view, name='admin_ajax_get_rng_run'),

    # Dedicated Admin Database Schema Integrity & Migration Sync Dashboard
    path('admin/schema-status/', admin_views.admin_database_schema_view, name='admin_schema_status'),

    # Dedicated Admin Supercar Cases Importer & Production Monitoring API
    path('admin/cases/supercars-import/', admin_views.admin_supercars_import_view, name='admin_supercars_import'),
    path('cases/supercars-status/', admin_views.supercars_status_api_view, name='supercars_status_api'),

    # SEO & Search Engine Indexation Endpoints
    path('robots.txt', robots_txt_view, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('favicon.ico', favicon_ico_view, name='favicon_ico'),
    path('site.webmanifest', webmanifest_view, name='webmanifest'),
    path('googlea35031ec8cebfe94.html', google_verification_file_view, name='google_verification_file'),

    path('admin/', admin.site.urls),
    path('', include('cases.urls', namespace='cases')),
    path('users/', include('users.urls', namespace='users')),
    path('inventory/', include('inventory.urls', namespace='inventory')),
    path('deposit/', include('payments.urls', namespace='payments')),
    path('upgrade/', include('upgrades.urls', namespace='upgrades')),
    path('contracts/', include('contracts.urls', namespace='contracts')),
    path('battles/', include('battles.urls', namespace='battles')),
]


def robust_media_serve(request, path, **kwargs):
    """
    Robust media file server for NEONDROP:
    1. Checks MEDIA_ROOT (disk).
    2. If not found on disk (e.g. Render Free ephemeral containers),
       seamlessly falls back to static/ and staticfiles/ directories
       where repository-tracked case artworks and item icons are permanently bundled.
    Guarantees zero broken images across all deployments and restarts.
    """
    media_file = Path(settings.MEDIA_ROOT) / path
    if media_file.is_file():
        return serve(request, path, document_root=str(settings.MEDIA_ROOT))

    static_file = Path(settings.BASE_DIR) / 'static' / path
    if static_file.is_file():
        return serve(request, path, document_root=str(Path(settings.BASE_DIR) / 'static'))

    if getattr(settings, 'STATIC_ROOT', None):
        staticfiles_file = Path(settings.STATIC_ROOT) / path
        if staticfiles_file.is_file():
            return serve(request, path, document_root=str(settings.STATIC_ROOT))

    resources_file = Path(settings.BASE_DIR) / 'cases' / 'resources' / path
    if resources_file.is_file():
        return serve(request, path, document_root=str(Path(settings.BASE_DIR) / 'cases' / 'resources'))

    return serve(request, path, document_root=str(settings.MEDIA_ROOT))


urlpatterns = urlpatterns + [
    # Media file direct serving with static fallback
    re_path(r'^media/(?P<path>.*)$', robust_media_serve),
]


handler400 = 'cases.views.custom_bad_request_view'
handler403 = 'cases.views.custom_permission_denied_view'
handler404 = 'cases.views.custom_page_not_found_view'
handler500 = 'cases.views.custom_server_error_view'

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
