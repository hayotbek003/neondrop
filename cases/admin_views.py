import os
import re
import csv
import time
import uuid
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
import json
from django.http import (
    HttpResponse,
    FileResponse,
    Http404,
    HttpResponseForbidden,
    JsonResponse,
    StreamingHttpResponse,
)

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


# ==============================================================================
# IMAGE-BASED MASS ITEM IMPORT & RTP CALCULATOR VIEWS
# ==============================================================================

from cases.rtp_calculator import calculate_rtp_chances, classify_tier, validate_case_chances
from cases.image_importer import PARADISE_ITEMS_METADATA, extract_items_from_grid_image, import_or_update_items
from django.db import transaction


def _can_manage_case_imports(user):
    return user.is_superuser or has_admin_perm(user, 'can_add_cases') or has_admin_perm(user, 'can_add_items')


@staff_member_required
@require_http_methods(["GET"])
def admin_image_import_view(request):
    """
    Dedicated GUI for uploading item grid screenshots, automatically recognizing
    and cropping items, adjusting prices, and calculating mathematically precise RTP odds.
    """
    if not _can_manage_case_imports(request.user):
        return HttpResponseForbidden("⛔ Ошибка доступа: требуются права на создание/редактирование кейсов (can_add_cases).")

    # Initial default items from «Райское извержение» preset
    initial_items = []
    for meta in PARADISE_ITEMS_METADATA:
        initial_items.append({
            'name': meta['name'],
            'weapon_type': meta['weapon_type'],
            'skin_name': meta['skin_name'],
            'rarity': meta['rarity'],
            'price': float(meta['value']),
            'image_url': f"{settings.MEDIA_URL}items/{meta['slug']}.png",
            'image_filename': f"{meta['slug']}.png",
            'slug': meta['slug'],
        })

    # Pre-calculate chances for initial 15 UC case at 90% RTP balanced mode
    calc_res = calculate_rtp_chances(
        [{'name': it['name'], 'price': it['price'], 'rarity': it['rarity']} for it in initial_items],
        case_price=Decimal("15.00"),
        target_rtp=0.90,
        mode='balanced'
    )

    # Attach calculated chance and tier to items
    chance_map = {item['name']: item for item in calc_res['items']}
    for it in initial_items:
        c_info = chance_map.get(it['name'], {})
        it['chance_pct'] = c_info.get('chance_pct', 0.0)
        it['tier'] = c_info.get('tier', 'Common')
        it['tier_class'] = c_info.get('tier_class', 'common')
        it['expected_contribution'] = c_info.get('expected_contribution', 0.0)

    context = {
        'title': '📦 Массовый импорт предметов из изображения & RTP Калькулятор',
        'app_label': 'cases',
        'is_nav_sidebar_enabled': True,
        'has_permission': True,
        'categories': Category.objects.all(),
        'themes': Case.THEME_CHOICES,
        'rarities': Item.RARITY_CHOICES,
        'initial_items_json': json.dumps(initial_items),
        'initial_summary_json': json.dumps({
            'case_price': float(calc_res['case_price']),
            'target_rtp': calc_res['target_rtp'],
            'actual_rtp': calc_res['actual_rtp'],
            'expected_return': calc_res['expected_return'],
            'house_edge': calc_res['house_edge'],
            'total_prob': calc_res['total_prob'],
            'tier_summary': calc_res['tier_summary'],
        }),
    }
    return render(request, 'admin/image_import.html', context)


@staff_member_required
@require_http_methods(["POST"])
def ajax_calculate_rtp_view(request):
    """
    AJAX endpoint: calculates odds based on dynamic item prices and target RTP / volatility.
    """
    if not _can_manage_case_imports(request.user):
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещён'}, status=403)

    try:
        data = json.loads(request.body.decode('utf-8'))
        items = data.get('items', [])
        if not items:
            return JsonResponse({'status': 'error', 'message': 'Список предметов пуст'}, status=400)

        case_price = Decimal(str(data.get('case_price', '15.00')))
        target_rtp_raw = float(data.get('target_rtp', 90.0))
        target_rtp = target_rtp_raw / 100.0 if target_rtp_raw > 1.0 else target_rtp_raw
        mode = data.get('mode', 'balanced')

        calc_result = calculate_rtp_chances(
            items=items,
            case_price=case_price,
            target_rtp=target_rtp,
            mode=mode
        )

        return JsonResponse({
            'status': 'success',
            'result': {
                'case_price': float(calc_result['case_price']),
                'target_rtp': calc_result['target_rtp'],
                'actual_rtp': calc_result['actual_rtp'],
                'expected_return': calc_result['expected_return'],
                'house_edge': calc_result['house_edge'],
                'total_prob': calc_result['total_prob'],
                'items': calc_result['items'],
                'tier_summary': calc_result['tier_summary']
            }
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@staff_member_required
@require_http_methods(["POST"])
def ajax_create_case_from_import_view(request):
    """
    AJAX endpoint: creates or updates a case, imports items, and sets CaseItem chances.
    Includes strict validation that chances sum to 100.000% before saving.
    """
    if not _can_manage_case_imports(request.user):
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещён'}, status=403)

    try:
        data = json.loads(request.body.decode('utf-8'))
        case_name = data.get('case_name', '').strip()
        case_slug = data.get('case_slug', '').strip()
        case_price = Decimal(str(data.get('case_price', '15.00')))
        color_theme = data.get('color_theme', 'demon-orange')
        category_slug = data.get('category_slug', 'limited')
        items_data = data.get('items', [])

        if not case_name:
            return JsonResponse({'status': 'error', 'message': 'Укажите название кейса'}, status=400)
        if not items_data:
            return JsonResponse({'status': 'error', 'message': 'Нет предметов для добавления в кейс'}, status=400)

        # Validate total probability sum
        total_prob = sum(float(it.get('chance_pct', 0.0)) for it in items_data)
        if abs(total_prob - 100.0) > 0.01:
            return JsonResponse({
                'status': 'error',
                'message': f'Сумма вероятностей составляет {total_prob:.3f}%, а должна быть ровно 100.000%! Нажмите «Пересчитать шансы».'
            }, status=400)

        with transaction.atomic():
            category = None
            if category_slug:
                category = Category.objects.filter(slug=category_slug).first()
                if not category:
                    category = Category.objects.create(name='Лимитированные кейсы', slug=category_slug, order=10)

            # 1. Create / Update items
            item_objs = []
            for it in items_data:
                item_name = it.get('name', '').strip()
                if not item_name:
                    continue
                
                weapon_type = it.get('weapon_type', 'Weapon')
                skin_name = it.get('skin_name', item_name)
                rarity = it.get('rarity', 'mil_spec')
                price = Decimal(str(it.get('price', '10.00')))
                img_rel = it.get('image_filename')
                image_path = f"items/{img_rel}" if img_rel else None

                item, _ = Item.objects.get_or_create(
                    name=item_name,
                    defaults={
                        'weapon_type': weapon_type,
                        'skin_name': skin_name,
                        'rarity': rarity,
                        'value': price,
                        'image': image_path
                    }
                )
                # Update properties if item already existed
                item.weapon_type = weapon_type
                item.skin_name = skin_name
                item.rarity = rarity
                item.value = price
                if image_path and not item.image:
                    item.image = image_path
                item.save()

                item_objs.append({
                    'item': item,
                    'chance_pct': float(it.get('chance_pct', 0.0))
                })

            # 2. Create / Update Case
            if not case_slug:
                from django.utils.text import slugify
                case_slug = slugify(case_name) or 'paradise-case'

            case, created = Case.objects.get_or_create(
                slug=case_slug,
                defaults={
                    'name': case_name,
                    'price': case_price,
                    'category': category,
                    'color_theme': color_theme,
                    'active': True,
                    'is_new': True,
                    'is_popular': True,
                }
            )

            case.name = case_name
            case.price = case_price
            case.category = category
            case.color_theme = color_theme
            case.active = True
            case.is_new = True
            case.is_popular = True

            # If cover image exists on disk, link it
            cover_path = Path(settings.MEDIA_ROOT) / 'cases' / 'paradise_eruption.jpg'
            if cover_path.exists():
                case.image = 'cases/paradise_eruption.jpg'

            case.save()

            # 3. Associate items and chances in CaseItem
            CaseItem.objects.filter(case=case).delete()
            created_case_items = []
            for entry in item_objs:
                created_case_items.append(
                    CaseItem(
                        case=case,
                        item=entry['item'],
                        weight=entry['chance_pct']
                    )
                )
            CaseItem.objects.bulk_create(created_case_items)

            # 4. Strict verification
            validate_case_chances(CaseItem.objects.filter(case=case))

        return JsonResponse({
            'status': 'success',
            'message': f'Кейс «{case.name}» успешно сохранён! Привязано предметов: {len(created_case_items)} с суммарной вероятностью 100.000%.',
            'case_id': case.id,
            'case_name': case.name,
            'case_slug': case.slug,
            'case_price': float(case.price),
            'case_url': f"/case/{case.slug}/",
            'admin_url': f"/admin/cases/case/{case.id}/change/"
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f"Ошибка сохранения: {str(e)}"}, status=400)


@staff_member_required
@require_http_methods(["POST"])
def ajax_upload_grid_image_view(request):
    """
    AJAX endpoint: receives an uploaded grid image screenshot, slices it into tiles,
    crops item icons, and returns metadata for the GUI table.
    """
    if not _can_manage_case_imports(request.user):
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещён'}, status=403)

    try:
        grid_file = request.FILES.get('grid_image')
        if not grid_file:
            return JsonResponse({'status': 'error', 'message': 'Файл изображения не загружен'}, status=400)

        # Save temporary file
        temp_dir = Path(settings.BASE_DIR) / 'temp_uploads'
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / grid_file.name

        with open(temp_path, 'wb+') as dest:
            for chunk in grid_file.chunks():
                dest.write(chunk)

        # Process extraction
        extracted_items = extract_items_from_grid_image(
            grid_image_path=str(temp_path),
            output_dir=os.path.join(settings.MEDIA_ROOT, 'items'),
            rows=4,
            cols=6
        )

        # Build response items
        items_response = []
        for it in extracted_items:
            items_response.append({
                'name': it['name'],
                'weapon_type': it.get('weapon_type', 'Weapon'),
                'skin_name': it.get('skin_name', it['name']),
                'rarity': it.get('rarity', 'mil_spec'),
                'price': float(it.get('value', 10.0)),
                'tier': it.get('tier', 'Common'),
                'image_url': f"{settings.MEDIA_URL}items/{it['slug']}.png",
                'image_filename': f"{it['slug']}.png",
                'slug': it['slug'],
            })

        return JsonResponse({
            'status': 'success',
            'message': f'Успешно распознано и нарезано {len(items_response)} предметов!',
            'items': items_response
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Ошибка обработки изображения: {str(e)}'}, status=400)


# ==============================================================================
# PROVABLY FAIR SERVER RNG MONTE CARLO SIMULATION VIEWS
# ==============================================================================
from cases.models import RngSimulationRun
from cases.rng_simulation_service import run_monte_carlo_simulation
from django.shortcuts import get_object_or_404


@staff_member_required
@require_http_methods(["GET"])
def admin_rng_simulation_view(request):
    """
    Dedicated Admin GUI View for Provably Fair Server-Side RNG Monte Carlo Simulation.
    Allows verifying mathematical accuracy, RTP convergence, and Chi-Square goodness-of-fit.
    """
    if not has_admin_perm(request.user, 'can_run_rng_simulation'):
        return HttpResponseForbidden("⛔ Ошибка доступа: у вас нет прав на симуляцию RNG (can_run_rng_simulation).")

    all_cases = list(Case.objects.prefetch_related('case_items__item').all().order_by('order', 'price'))
    cases_meta = {}
    cases_list = []

    for c in all_cases:
        items = list(c.case_items.all())
        total_w = sum(ci.weight for ci in items)
        if total_w > 0:
            target_ev = sum((ci.weight / total_w) * float(ci.item.value) for ci in items)
        else:
            target_ev = 0.0
        price = float(c.price)
        target_rtp = (target_ev / price * 100.0) if price > 0 else 0.0

        c_info = {
            'id': c.id,
            'name': c.name,
            'slug': c.slug,
            'price': price,
            'items_count': len(items),
            'target_rtp': round(target_rtp, 2),
            'target_ev': round(target_ev, 2),
            'house_edge': round(max(0.0, 100.0 - target_rtp), 2),
        }
        cases_meta[str(c.id)] = c_info
        cases_list.append(c_info)

    try:
        recent_runs = list(RngSimulationRun.objects.select_related('case', 'user').order_by('-created_at')[:15])
    except Exception:
        try:
            from django.core.management import call_command
            call_command('migrate', interactive=False)
            recent_runs = list(RngSimulationRun.objects.select_related('case', 'user').order_by('-created_at')[:15])
        except Exception:
            recent_runs = []

    context = {
        'title': '🎲 Симуляция честного серверного RNG (Monte Carlo Test)',
        'app_label': 'cases',
        'is_nav_sidebar_enabled': True,
        'has_permission': True,
        'cases': cases_list,
        'cases_meta_json': json.dumps(cases_meta),
        'recent_runs': recent_runs,
    }
    return render(request, 'admin/rng_simulation.html', context)


@staff_member_required
@require_http_methods(["POST"])
def ajax_run_rng_simulation_view(request):
    """
    AJAX endpoint to execute Monte Carlo simulation for selected case.
    Strictly non-destructive: zero writes to Opening, Transaction, InventoryItem, Profile.
    """
    if not has_admin_perm(request.user, 'can_run_rng_simulation'):
        return JsonResponse({'status': 'error', 'message': '⛔ Ошибка доступа: у вас нет прав на симуляцию RNG.'}, status=403)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST

        case_id = data.get('case_id')
        num_simulations = int(data.get('num_simulations', 100000))

        if not case_id:
            return JsonResponse({'status': 'error', 'message': 'Выберите кейс для симуляции.'}, status=400)

        case = Case.objects.filter(id=case_id).first()
        if not case:
            return JsonResponse({'status': 'error', 'message': 'Выбранный кейс не найден.'}, status=404)

        if not case.case_items.exists():
            return JsonResponse({'status': 'error', 'message': 'В выбранном кейсе нет предметов для проведения симуляции.'}, status=400)

        result = run_monte_carlo_simulation(
            case=case,
            num_simulations=num_simulations,
            user=request.user,
            save_run=True
        )

        return JsonResponse({
            'status': 'success',
            'data': result
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Ошибка проведения симуляции: {str(e)}'}, status=400)


@staff_member_required
@require_http_methods(["GET"])
def ajax_get_rng_simulation_run_view(request, run_id):
    """
    AJAX endpoint to retrieve details of a previous simulation run.
    """
    if not has_admin_perm(request.user, 'can_run_rng_simulation'):
        return JsonResponse({'status': 'error', 'message': '⛔ Ошибка доступа: у вас нет прав на симуляцию RNG.'}, status=403)

    run_record = get_object_or_404(RngSimulationRun, id=run_id)
    return JsonResponse({
        'status': 'success',
        'data': {
            'run_id': run_record.id,
            'case_id': run_record.case_id,
            'case_name': run_record.case.name,
            'case_price': float(run_record.case_price),
            'num_simulations': run_record.num_simulations,
            'total_spent': float(run_record.total_spent),
            'total_payout': float(run_record.total_payout),
            'target_rtp': run_record.target_rtp,
            'actual_rtp': run_record.actual_rtp,
            'deviation': run_record.deviation,
            'house_edge': run_record.house_edge,
            'chi_square_stat': run_record.chi_square_stat,
            'p_value': run_record.p_value,
            'status': run_record.status,
            'status_level': run_record.status_level,
            'ci_lower': run_record.ci_lower,
            'ci_upper': run_record.ci_upper,
            'server_seed': run_record.server_seed,
            'client_seed': run_record.client_seed,
            'items': run_record.item_stats,
            'created_at': run_record.created_at.strftime('%d.%m.%Y %H:%M:%S'),
        }
    })


# =========================================================================
# DEDICATED PUBG ITEM ZIP IMPORTER (Validation, Preview, Atomic Import)
# =========================================================================
from .pubg_importer_service import PubgZipImporter, PubgImportValidationError


def _get_pubg_import_temp_dir() -> Path:
    d = Path(tempfile.gettempdir()) / 'neondrop_pubg_imports'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clean_old_pubg_temp_files(max_age_seconds: int = 3600):
    try:
        temp_dir = _get_pubg_import_temp_dir()
        now = time.time()
        for f in temp_dir.glob('*.zip'):
            if now - f.stat().st_mtime > max_age_seconds:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass


@staff_member_required
@require_http_methods(["GET", "POST"])
def admin_pubg_import_view(request):
    """
    Main Django Admin GUI for uploading, validating, previewing, and importing PUBG items from ZIP.
    """
    if not (request.user.is_superuser or has_admin_perm(request.user, 'can_add_items')):
        return HttpResponseForbidden("⛔ Ошибка доступа: у вас нет прав на добавление предметов (can_add_items).")

    _clean_old_pubg_temp_files()

    context = {
        'title': 'Импорт PUBG предметов (ZIP)',
        'app_label': 'cases',
        'is_nav_sidebar_enabled': True,
        'has_permission': True,
        'step': 'upload',
    }

    # Reset preview
    if request.method == 'GET' and request.GET.get('reset'):
        token = request.session.pop('pubg_import_token', None)
        if token:
            temp_file = _get_pubg_import_temp_dir() / f"{token}.zip"
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
        return redirect('admin_pubg_import')

    # STEP 1: Upload & Inspect
    if request.method == 'POST' and request.POST.get('action') == 'preview':
        uploaded_file = request.FILES.get('zip_file')
        if not uploaded_file:
            messages.error(request, "Пожалуйста, выберите .zip файл для импорта.")
            return render(request, 'admin/pubg_import.html', context)

        fname = uploaded_file.name.lower()
        if not (fname.endswith('.zip') or '.zip' in fname):
            messages.error(request, "Неверный формат файла. Разрешены только архивы .zip.")
            return render(request, 'admin/pubg_import.html', context)

        token = uuid.uuid4().hex
        temp_path = _get_pubg_import_temp_dir() / f"{token}.zip"

        try:
            with open(temp_path, 'wb') as dest:
                for chunk in uploaded_file.chunks():
                    dest.write(chunk)

            importer = PubgZipImporter(str(temp_path))
            inspection = importer.validate_and_inspect()

            if not inspection['is_valid']:
                temp_path.unlink(missing_ok=True)
                context['inspection_errors'] = inspection['errors_list']
                context['error_items_count'] = inspection['error_items']
                messages.error(
                    request,
                    f"⚠️ Валидация ZIP не пройдена: обнаружено ошибок: {inspection['error_items']}. "
                    "Частичный импорт отменён. Исправьте ошибки в архиве и загрузите снова."
                )
                return render(request, 'admin/pubg_import.html', context)

            request.session['pubg_import_token'] = token
            context['step'] = 'preview'
            context['token'] = token
            context['inspection'] = inspection
            context['filename'] = uploaded_file.name
            context['filesize_mb'] = round(uploaded_file.size / (1024 * 1024), 2)
            return render(request, 'admin/pubg_import.html', context)

        except PubgImportValidationError as e:
            temp_path.unlink(missing_ok=True)
            messages.error(request, f"Ошибка валидации: {e}")
            return render(request, 'admin/pubg_import.html', context)
        except Exception as e:
            temp_path.unlink(missing_ok=True)
            messages.error(request, f"Непредвиденная ошибка при обработке архива: {e}")
            return render(request, 'admin/pubg_import.html', context)

    # STEP 2: Synchronous execution fallback
    if request.method == 'POST' and request.POST.get('action') == 'execute':
        token = request.POST.get('token') or request.session.get('pubg_import_token')
        mode = request.POST.get('mode', 'add_only')
        if mode not in ['add_only', 'update_existing']:
            mode = 'add_only'

        if not token:
            messages.error(request, "Сессия импорта устарела. Загрузите файл заново.")
            return redirect('admin_pubg_import')

        temp_path = _get_pubg_import_temp_dir() / f"{token}.zip"
        if not temp_path.exists():
            messages.error(request, "Временный файл импорта не найден или истёк срок действия. Загрузите файл заново.")
            return redirect('admin_pubg_import')

        try:
            importer = PubgZipImporter(str(temp_path))
            summary = importer.execute_import(mode=mode)
            temp_path.unlink(missing_ok=True)
            request.session.pop('pubg_import_token', None)

            context['step'] = 'completed'
            context['summary'] = summary
            context['mode'] = mode
            messages.success(request, "✅ Импорт PUBG-предметов успешно завершён!")
            return render(request, 'admin/pubg_import.html', context)

        except PubgImportValidationError as e:
            messages.error(request, f"Ошибка валидации при импорте: {e}")
            return redirect('admin_pubg_import')
        except Exception as e:
            messages.error(request, f"Ошибка импорта: {e}")
            return redirect('admin_pubg_import')

    return render(request, 'admin/pubg_import.html', context)


@staff_member_required
@require_http_methods(["POST"])
def admin_pubg_import_stream_view(request):
    """
    NDJSON streaming endpoint for real-time progress reporting during PUBG import.
    Emits lines of JSON:
      {"event": "progress", "current": 125, "total": 1000, "item": "..."}
      {"event": "complete", "summary": {...}}
      {"event": "error", "message": "..."}
    """
    if not (request.user.is_superuser or has_admin_perm(request.user, 'can_add_items')):
        return JsonResponse({'status': 'error', 'message': 'Forbidden'}, status=403)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    token = data.get('token')
    mode = data.get('mode', 'add_only')
    if mode not in ['add_only', 'update_existing']:
        mode = 'add_only'

    if not token or not re.match(r'^[a-f0-9]{32}$', token):
        return JsonResponse({'status': 'error', 'message': 'Недействительный токен импорта.'}, status=400)

    temp_path = _get_pubg_import_temp_dir() / f"{token}.zip"
    if not temp_path.exists():
        return JsonResponse({'status': 'error', 'message': 'Файл импорта не найден или истёк срок сессии.'}, status=404)

    def event_stream():
        try:
            importer = PubgZipImporter(str(temp_path))

            class ProgressEmitter:
                def __init__(self):
                    self.buffer = []

                def callback(self, current, total, item_name):
                    msg = json.dumps({
                        'event': 'progress',
                        'current': current,
                        'total': total,
                        'item': item_name,
                        'percent': int((current / total) * 100) if total else 100,
                    })
                    self.buffer.append(msg + "\n")

            emitter = ProgressEmitter()
            summary = importer.execute_import(mode=mode, progress_callback=emitter.callback)

            for line in emitter.buffer:
                yield line

            complete_msg = json.dumps({
                'event': 'complete',
                'summary': summary,
            })
            yield f"{complete_msg}\n"

        except Exception as e:
            err_msg = json.dumps({
                'event': 'error',
                'message': str(e),
            })
            yield f"{err_msg}\n"
        finally:
            temp_path.unlink(missing_ok=True)

    response = StreamingHttpResponse(event_stream(), content_type='application/x-ndjson')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@staff_member_required
@require_http_methods(["GET"])
def admin_pubg_import_thumb_view(request, token, image_path):
    """
    Lightweight endpoint to serve thumbnail images from the temporary uploaded ZIP for preview.
    """
    if not (request.user.is_superuser or has_admin_perm(request.user, 'can_add_items')):
        return HttpResponseForbidden("Forbidden")

    if not re.match(r'^[a-f0-9]{32}$', token):
        raise Http404("Invalid token")

    temp_path = _get_pubg_import_temp_dir() / f"{token}.zip"
    if not temp_path.exists():
        raise Http404("Zip not found")

    try:
        with zipfile.ZipFile(temp_path, 'r') as zf:
            norm_map = {n.replace('\\', '/').strip('/'): n for n in zf.namelist()}
            clean_path = image_path.replace('\\', '/').strip('/')
            actual_name = norm_map.get(clean_path)
            if not actual_name:
                matches = [v for k, v in norm_map.items() if k.endswith(clean_path)]
                if matches:
                    actual_name = matches[0]

            if not actual_name:
                raise Http404("Image not in zip")

            data = zf.read(actual_name)
            ext = Path(actual_name).suffix.lower()
            ct = 'image/webp' if ext == '.webp' else ('image/png' if ext == '.png' else 'image/jpeg')
            return HttpResponse(data, content_type=ct)
    except Exception:
        raise Http404("Error reading image")
