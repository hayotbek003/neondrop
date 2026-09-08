import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import models, transaction
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST

from .models import AdminPermissionProfile, ADMIN_PERMISSIONS_LIST

audit_logger = logging.getLogger('neondrop.audit')
security_logger = logging.getLogger('neondrop.security')


PERMISSION_GROUPS = [
    ('👥 Пользователи', [
        ('can_view_users', 'Просматривать пользователей', 'Доступ к просмотру списка и карточек игроков'),
        ('can_edit_users', 'Редактировать пользователей', 'Изменение данных профиля и статусов'),
    ]),
    ('📦 Кейсы', [
        ('can_view_cases', 'Просматривать кейсы', 'Просмотр каталога кейсов в панели'),
        ('can_add_cases', 'Добавлять кейсы', 'Создание новых кейсов'),
        ('can_edit_cases', 'Редактировать кейсы', 'Изменение описания, темы и параметров кейсов'),
        ('can_delete_cases', 'Удалять кейсы', 'Удаление кейсов из системы'),
    ]),
    ('🔫 Предметы и цены / шансы', [
        ('can_add_items', 'Добавлять предметы', 'Добавление новых скинов в базу данных'),
        ('can_edit_images', 'Изменять изображения', 'Загрузка и обновление скинов/кейсов'),
        ('can_edit_prices', 'Изменять цены', 'Изменение цен на скины и кейсы'),
        ('can_edit_case_chances', 'Изменять шансы кейсов', 'Настройка весов выпадения и персональных шансов'),
    ]),
    ('🎟️ Промокоды и блогеры', [
        ('can_manage_promocodes', 'Управлять промокодами', 'Создание и редактирование промокодов'),
        ('can_view_blogger_stats', 'Просматривать статистику блогеров', 'Доступ к дашборду аналитики и отчетам'),
        ('can_edit_blogger_percent', 'Изменять процент блогеров', 'Установка персонального % отчислений'),
    ]),
    ('💳 Финансы (пополнения и выводы)', [
        ('can_view_deposits', 'Просматривать пополнения', 'Журнал заявок на депозит'),
        ('can_approve_deposits', 'Подтверждать пополнения', 'Одобрение платежей и зачисление UC'),
        ('can_view_withdrawals', 'Просматривать выводы', 'Журнал заявок на вывод скинов/средств'),
        ('can_approve_withdrawals', 'Одобрять выводы', 'Подтверждение вывода или возврат средств'),
    ]),
    ('💾 Резервные копии (Backup)', [
        ('can_view_backup', 'Просматривать Backup', 'Доступ к разделу резервного копирования'),
        ('can_create_backup', 'Делать Backup', 'Генерация и скачивание полного ZIP архива'),
        ('can_restore_backup', 'Восстанавливать Backup', 'Загрузка и накат резервной копии'),
    ]),
]


def administrators_dashboard_view(request):
    """
    Dedicated Cyberpunk Admin page for Administrator Management («👑 Управление администраторами»).
    Strictly protected: ONLY superusers (is_superuser=True) can access.
    """
    if not request.user.is_authenticated or not request.user.is_active:
        return redirect('admin:login')
    if not request.user.is_superuser:
        security_logger.warning(
            f"ADMIN_MANAGEMENT_ACCESS_DENIED: User '{request.user.username}' attempted to access /admin/administrators/"
        )
        return HttpResponseForbidden("Доступ запрещен. Только Главный Администратор может управлять администраторами.")

    # Search filter
    q = request.GET.get('q', '').strip()
    
    # Query all administrators (staff or superusers)
    admins_qs = User.objects.filter(models.Q(is_staff=True) | models.Q(is_superuser=True)).distinct().select_related('profile', 'admin_permissions').order_by('-is_superuser', 'username')
    if q:
        admins_qs = admins_qs.filter(
            models.Q(username__icontains=q) |
            models.Q(email__icontains=q) |
            models.Q(id__icontains=q)
        )

    # Search candidates for new admin appointment
    candidate_users = []
    candidate_q = request.GET.get('user_search', '').strip()
    if candidate_q:
        candidate_users = User.objects.filter(
            is_staff=False,
            is_superuser=False
        ).filter(
            models.Q(username__icontains=candidate_q) |
            models.Q(email__icontains=candidate_q) |
            models.Q(id__icontains=candidate_q)
        ).select_related('profile').order_by('username')[:15]

    # Pre-populate active permission flags for modal views
    admins_data = []
    for admin_user in admins_qs:
        perms_profile = getattr(admin_user, 'admin_permissions', None)
        active_perms = []
        if admin_user.is_superuser:
            role_label = "Главный Администратор"
            role_badge = "badge-neon-purple"
            active_perms_count = len(ADMIN_PERMISSIONS_LIST)
            total_perms_count = len(ADMIN_PERMISSIONS_LIST)
        else:
            role_label = "Администратор"
            role_badge = "badge-neon-cyan"
            if perms_profile:
                active_perms_count = perms_profile.active_permissions_count()
                for perm_code, perm_title, _ in ADMIN_PERMISSIONS_LIST:
                    if getattr(perms_profile, perm_code, False):
                        active_perms.append((perm_code, perm_title))
            else:
                active_perms_count = 0
            total_perms_count = len(ADMIN_PERMISSIONS_LIST)

        # Dictionary of flags for quick template lookup
        flags = {}
        for perm_code, _, _ in ADMIN_PERMISSIONS_LIST:
            flags[perm_code] = getattr(perms_profile, perm_code, False) if perms_profile else False

        admins_data.append({
            'user': admin_user,
            'role_label': role_label,
            'role_badge': role_badge,
            'active_perms_count': active_perms_count,
            'total_perms_count': total_perms_count,
            'active_perms': active_perms,
            'flags': flags,
            'is_self': admin_user.pk == request.user.pk,
        })

    context = {
        'title': '👑 Управление администраторами',
        'app_label': 'users',
        'is_nav_sidebar_enabled': True,
        'has_permission': True,
        'admins_data': admins_data,
        'permission_groups': PERMISSION_GROUPS,
        'all_permissions': ADMIN_PERMISSIONS_LIST,
        'q': q,
        'candidate_q': candidate_q,
        'candidate_users': candidate_users,
        'total_admins_count': admins_qs.count(),
        'superusers_count': admins_qs.filter(is_superuser=True).count(),
        'staff_count': admins_qs.filter(is_superuser=False, is_staff=True).count(),
    }
    return render(request, 'admin/administrators.html', context)


@require_POST
def assign_admin_view(request):
    """
    Superuser action to promote an existing user to Administrator (is_staff=True)
    and set granular permissions.
    """
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden("Доступ запрещен.")

    user_id = request.POST.get('user_id')
    user = get_object_or_404(User, id=user_id)

    with transaction.atomic():
        user.is_staff = True
        user.save(update_fields=['is_staff'])

        perm_profile, _ = AdminPermissionProfile.objects.get_or_create(user=user)

        active_codes = []
        for perm_code, _, _ in ADMIN_PERMISSIONS_LIST:
            is_checked = request.POST.get(f"perm_{perm_code}") == '1'
            setattr(perm_profile, perm_code, is_checked)
            if is_checked:
                active_codes.append(perm_code)

        perm_profile.save()

    audit_logger.info(
        f"ADMIN_PROMOTED: user='{user.username}' (id={user.id}) appointed staff admin by '{request.user.username}', "
        f"perms_count={len(active_codes)} [{', '.join(active_codes)}]"
    )
    messages.success(request, f"👑 Пользователь {user.username} успешно назначен администратором с {len(active_codes)} правами!")
    return redirect('admin_administrators')


@require_POST
def update_admin_perms_view(request, user_id):
    """
    Superuser action to update granular permissions for an existing administrator.
    """
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden("Доступ запрещен.")

    target_user = get_object_or_404(User, id=user_id)

    # Protect main administrators: regular staff permissions don't override superuser
    with transaction.atomic():
        perm_profile, _ = AdminPermissionProfile.objects.get_or_create(user=target_user)

        active_codes = []
        for perm_code, _, _ in ADMIN_PERMISSIONS_LIST:
            is_checked = request.POST.get(f"perm_{perm_code}") == '1'
            setattr(perm_profile, perm_code, is_checked)
            if is_checked:
                active_codes.append(perm_code)

        perm_profile.save()

    audit_logger.info(
        f"ADMIN_PERMISSIONS_UPDATED: user='{target_user.username}' updated by '{request.user.username}', "
        f"active_perms={len(active_codes)} [{', '.join(active_codes)}]"
    )
    messages.success(request, f"✓ Права администратора {target_user.username} успешно обновлены ({len(active_codes)} прав активно).")
    return redirect('admin_administrators')


@require_POST
def toggle_admin_status_view(request, user_id):
    """
    Superuser action to block / unblock an administrator account (is_active).
    Prevents self-locking.
    """
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden("Доступ запрещен.")

    target_user = get_object_or_404(User, id=user_id)

    if target_user.pk == request.user.pk:
        messages.error(request, "⚠️ Вы не можете заблокировать собственную учетную запись!")
        return redirect('admin_administrators')

    new_status = not target_user.is_active
    target_user.is_active = new_status
    target_user.save(update_fields=['is_active'])

    action_name = "разблокирован" if new_status else "заблокирован"
    audit_logger.info(
        f"ADMIN_STATUS_CHANGED: user='{target_user.username}' is_active={new_status} by '{request.user.username}'"
    )
    messages.success(request, f"Аккаунт администратора {target_user.username} успешно {action_name}.")
    return redirect('admin_administrators')


@require_POST
def revoke_admin_view(request, user_id):
    """
    Superuser action to completely remove administrator privileges from a user.
    Sets is_staff=False and deletes AdminPermissionProfile.
    Prevents revoking self or superusers.
    """
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden("Доступ запрещен.")

    target_user = get_object_or_404(User, id=user_id)

    if target_user.pk == request.user.pk:
        messages.error(request, "⚠️ Вы не можете снять права администратора с себя!")
        return redirect('admin_administrators')

    if target_user.is_superuser:
        messages.error(request, "⚠️ Нельзя снять права с Главного Администратора (superuser) через эту форму.")
        return redirect('admin_administrators')

    with transaction.atomic():
        target_user.is_staff = False
        target_user.save(update_fields=['is_staff'])
        AdminPermissionProfile.objects.filter(user=target_user).delete()

    audit_logger.info(
        f"ADMIN_REVOKED: user='{target_user.username}' (id={target_user.id}) revoked by '{request.user.username}'"
    )
    messages.warning(request, f"Права администратора для пользователя {target_user.username} успешно отозваны.")
    return redirect('admin_administrators')
