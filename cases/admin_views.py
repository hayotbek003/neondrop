import os
import csv
import tempfile
from pathlib import Path
from datetime import datetime
from decimal import Decimal

from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import HttpResponse, FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.contrib.auth.models import User

from cases.models import Case, Item, CaseItem, Opening, PromoCode, Category
from inventory.models import InventoryItem
from payments.models import Transaction
from .backup_restore_service import (
    create_full_backup_zip,
    inspect_backup_zip,
    restore_from_backup_zip,
    BackupRestoreError,
    MODELS_EXPORT_ORDER,
)
from users.models import has_admin_perm


@staff_member_required
@require_http_methods(["GET", "POST"])
def admin_backup_restore_view(request):
    """
    Main GUI page in Django Admin for NEONDROP Backup & Restore.
    Supports:
    - Downloading consolidated single ZIP backup
    - Safe upload and non-destructive preview inspection
    - Transactional confirmation of restoration with pre-restore auto-backup
    """
    if not has_admin_perm(request.user, 'can_view_backup'):
        return HttpResponseForbidden("⛔ Ошибка доступа: у вас нет прав на просмотр резервных копий (can_view_backup).")

    context = {
        'title': 'Backup / Restore данных NEONDROP',
        'app_label': 'cases',
        'is_nav_sidebar_enabled': True,
        'has_permission': True,
        'current_stats': {
            'users_count': User.objects.count(),
            'cases_count': Case.objects.count(),
            'items_count': Item.objects.count(),
            'case_items_count': CaseItem.objects.count(),
            'inventory_count': InventoryItem.objects.count(),
            'openings_count': Opening.objects.count(),
            'transactions_count': Transaction.objects.count(),
            'promocodes_count': PromoCode.objects.count(),
        }
    }

    # Action 1: Upload and Preview
    if request.method == 'POST' and request.POST.get('action') == 'inspect':
        if not has_admin_perm(request.user, 'can_restore_backup'):
            messages.error(request, "⛔ Ошибка доступа: у вас нет прав на восстановление базы данных (can_restore_backup).")
            return render(request, 'admin/backup_restore.html', context)

        uploaded_file = request.FILES.get('backup_file')
        if not uploaded_file:
            messages.error(request, "Пожалуйста, выберите .zip файл резервной копии.")
            return render(request, 'admin/backup_restore.html', context)

        if not uploaded_file.name.lower().endswith('.zip'):
            messages.error(request, "Поддерживаются только архивы формата .zip.")
            return render(request, 'admin/backup_restore.html', context)

        try:
            # Save uploaded file to secure temporary location
            temp_dir = Path(tempfile.gettempdir()) / 'neondrop_restore_uploads'
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / f"pending_restore_{request.user.id}_{int(datetime.utcnow().timestamp())}.zip"
            
            with open(temp_file_path, 'wb') as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)

            preview = inspect_backup_zip(temp_file_path)
            request.session['pending_restore_path'] = str(temp_file_path)
            context['preview'] = preview
            context['uploaded_filename'] = uploaded_file.name
            messages.info(request, "Архив проверен. Ознакомьтесь с данными перед подтверждением восстановления.")

        except BackupRestoreError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ошибка при обработке файла: {e}")

        return render(request, 'admin/backup_restore.html', context)

    # Action 2: Confirm Restore
    elif request.method == 'POST' and request.POST.get('action') == 'confirm':
        if not has_admin_perm(request.user, 'can_restore_backup'):
            messages.error(request, "⛔ Ошибка доступа: у вас нет прав на восстановление базы данных (can_restore_backup).")
            return render(request, 'admin/backup_restore.html', context)

        temp_file_str = request.session.get('pending_restore_path')
        if not temp_file_str or not Path(temp_file_str).exists():
            # Check if file was uploaded directly in the confirm form
            if 'backup_file' in request.FILES:
                uploaded_file = request.FILES['backup_file']
                temp_dir = Path(tempfile.gettempdir()) / 'neondrop_restore_uploads'
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_file_path = temp_dir / f"direct_restore_{request.user.id}_{int(datetime.utcnow().timestamp())}.zip"
                with open(temp_file_path, 'wb') as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)
                temp_file_str = str(temp_file_path)
            else:
                messages.error(request, "Файл для восстановления не найден или сессия устарела. Загрузите архив снова.")
                return render(request, 'admin/backup_restore.html', context)

        try:
            result = restore_from_backup_zip(temp_file_str, auto_backup=True, user=request.user)
            context['restore_result'] = result
            messages.success(
                request,
                f"✅ Восстановление завершено успешно! Восстановлено записей: {result['total_restored']}, "
                f"медиа-файлов: {result['extracted_media']}. Все связи и шансы сохранены."
            )
        except BackupRestoreError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Непредвиденная ошибка при восстановлении: {e}")
        finally:
            # Clean up temporary file
            try:
                if temp_file_str and Path(temp_file_str).exists():
                    os.remove(temp_file_str)
            except Exception:
                pass
            request.session.pop('pending_restore_path', None)

        # Refresh stats after restore
        context['current_stats'] = {
            'users_count': User.objects.count(),
            'cases_count': Case.objects.count(),
            'items_count': Item.objects.count(),
            'case_items_count': CaseItem.objects.count(),
            'inventory_count': InventoryItem.objects.count(),
            'openings_count': Opening.objects.count(),
            'transactions_count': Transaction.objects.count(),
            'promocodes_count': PromoCode.objects.count(),
        }
        return render(request, 'admin/backup_restore.html', context)

    # Action 3: Cancel Preview
    elif request.method == 'POST' and request.POST.get('action') == 'cancel':
        temp_file_str = request.session.pop('pending_restore_path', None)
        if temp_file_str and Path(temp_file_str).exists():
            try:
                os.remove(temp_file_str)
            except Exception:
                pass
        messages.info(request, "Восстановление отменено.")
        return redirect('admin_backup_restore')

    return render(request, 'admin/backup_restore.html', context)


@staff_member_required
def admin_backup_download_view(request):
    """
    Generates on-the-fly and downloads a consolidated single ZIP archive:
    neondrop_backup_YYYY-MM-DD_HH-MM-SS.zip
    Contains database.json, metadata.json, and all media/ files.
    """
    if not has_admin_perm(request.user, 'can_create_backup'):
        return HttpResponseForbidden("⛔ Ошибка доступа: у вас нет прав на скачивание/создание резервной копии (can_create_backup).")

    try:
        archive_path, metadata = create_full_backup_zip(include_media=True)
        response = FileResponse(
            open(archive_path, 'rb'),
            content_type='application/zip',
            as_attachment=True,
            filename=archive_path.name
        )
        return response
    except Exception as e:
        messages.error(request, f"Ошибка создания резервной копии: {e}")
        return redirect('admin_backup_restore')


# =========================================================================
# CSV EXPORT UTILITIES (Detailed Reports for Cases, Users, Items, Finances)
# =========================================================================

def _create_csv_response(filename, fieldnames, rows):
    """Helper to stream utf-8-sig CSV response with Excel compatibility."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.DictWriter(response, fieldnames=fieldnames, delimiter=';')
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return response


@staff_member_required
def export_users_csv_view(request):
    """Exports all registered users with balance and metadata."""
    fieldnames = ['ID', 'Username', 'Email', 'Баланс (UC)', 'Всего открытий', 'Выигрыши (UC)', 'Staff', 'Superuser', 'Дата регистрации']
    rows = []
    for user in User.objects.select_related('profile').order_by('id'):
        balance = getattr(user.profile, 'balance', Decimal('0.00')) if hasattr(user, 'profile') else Decimal('0.00')
        opened = getattr(user.profile, 'total_opened', 0) if hasattr(user, 'profile') else 0
        won = getattr(user.profile, 'total_winnings', Decimal('0.00')) if hasattr(user, 'profile') else Decimal('0.00')
        rows.append({
            'ID': user.id,
            'Username': user.username,
            'Email': user.email,
            'Баланс (UC)': balance,
            'Всего открытий': opened,
            'Выигрыши (UC)': won,
            'Staff': 'Да' if user.is_staff else 'Нет',
            'Superuser': 'Да' if user.is_superuser else 'Нет',
            'Дата регистрации': user.date_joined.strftime('%d.%m.%Y %H:%M') if user.date_joined else '',
        })
    filename = f"neondrop_users_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return _create_csv_response(filename, fieldnames, rows)


@staff_member_required
def export_cases_csv_view(request):
    """Exports all cases with pricing and configuration."""
    fieldnames = ['ID', 'Название', 'Slug', 'Цена (UC)', 'Категория', 'Цветовая тема', 'Активен', 'Популярный', 'Новый', 'Предметов внутри']
    rows = []
    for c in Case.objects.select_related('category').prefetch_related('case_items').order_by('order', 'price'):
        rows.append({
            'ID': c.id,
            'Название': c.name,
            'Slug': c.slug,
            'Цена (UC)': c.price,
            'Категория': c.category.name if c.category else '',
            'Цветовая тема': c.color_theme,
            'Активен': 'Да' if c.active else 'Нет',
            'Популярный': 'Да' if c.is_popular else 'Нет',
            'Новый': 'Да' if c.is_new else 'Нет',
            'Предметов внутри': c.case_items.count(),
        })
    filename = f"neondrop_cases_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return _create_csv_response(filename, fieldnames, rows)


@staff_member_required
def export_items_csv_view(request):
    """Exports all skins/items with pricing and rarity."""
    fieldnames = ['ID', 'Название', 'Тип оружия', 'Скин', 'Стоимость (UC)', 'Редкость', 'Цвет', 'Изображение / URL']
    rows = []
    for item in Item.objects.all().order_by('-value'):
        rows.append({
            'ID': item.id,
            'Название': item.name,
            'Тип оружия': item.weapon_type,
            'Скин': item.skin_name,
            'Стоимость (UC)': item.value,
            'Редкость': item.get_rarity_display(),
            'Цвет': item.rarity_color,
            'Изображение / URL': item.display_image or '',
        })
    filename = f"neondrop_items_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return _create_csv_response(filename, fieldnames, rows)


@staff_member_required
def export_case_contents_csv_view(request):
    """
    Exports detailed case containments with EXACT weights and calculated chances (%).
    """
    fieldnames = ['ID кейса', 'Кейс', 'Цена кейса (UC)', 'ID предмета', 'Предмет', 'Редкость', 'Цена предмета (UC)', 'Вес', 'Шанс выпадения (%)']
    rows = []
    for case in Case.objects.prefetch_related('case_items__item').order_by('order', 'price'):
        case_items = list(case.case_items.all())
        total_weight = sum(ci.weight for ci in case_items)
        for ci in sorted(case_items, key=lambda x: x.weight, reverse=True):
            pct = round((ci.weight / total_weight) * 100.0, 4) if total_weight > 0 else 0.0
            rows.append({
                'ID кейса': case.id,
                'Кейс': case.name,
                'Цена кейса (UC)': case.price,
                'ID предмета': ci.item.id,
                'Предмет': ci.item.name,
                'Редкость': ci.item.get_rarity_display(),
                'Цена предмета (UC)': ci.item.value,
                'Вес': ci.weight,
                'Шанс выпадения (%)': f"{pct:.4f}%",
            })
    filename = f"neondrop_case_contents_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return _create_csv_response(filename, fieldnames, rows)


@staff_member_required
def export_openings_csv_view(request):
    """Exports case openings history."""
    fieldnames = ['ID', 'Пользователь', 'Кейс', 'Выпавший предмет', 'Цена кейса (UC)', 'Цена скина (UC)', 'Дата открытия']
    rows = []
    for op in Opening.objects.select_related('user', 'case', 'item').order_by('-created_at')[:5000]:
        rows.append({
            'ID': op.id,
            'Пользователь': op.user.username,
            'Кейс': op.case.name,
            'Выпавший предмет': op.item.name,
            'Цена кейса (UC)': op.price,
            'Цена скина (UC)': op.item.value,
            'Дата открытия': op.created_at.strftime('%d.%m.%Y %H:%M:%S'),
        })
    filename = f"neondrop_openings_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return _create_csv_response(filename, fieldnames, rows)


@staff_member_required
def export_transactions_csv_view(request):
    """Exports financial ledger transactions."""
    fieldnames = ['ID', 'Пользователь', 'Сумма (UC)', 'Баланс до (UC)', 'Баланс после (UC)', 'Тип операции', 'Статус', 'Метод', 'Описание', 'Дата']
    rows = []
    for tx in Transaction.objects.select_related('user').order_by('-created_at')[:5000]:
        rows.append({
            'ID': tx.id,
            'Пользователь': tx.user.username,
            'Сумма (UC)': tx.amount,
            'Баланс до (UC)': tx.balance_before,
            'Баланс после (UC)': tx.balance_after,
            'Тип операции': tx.get_transaction_type_display(),
            'Статус': tx.get_status_display(),
            'Метод': tx.get_payment_method_display(),
            'Описание': tx.description or '',
            'Дата': tx.created_at.strftime('%d.%m.%Y %H:%M:%S'),
        })
    filename = f"neondrop_transactions_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return _create_csv_response(filename, fieldnames, rows)
