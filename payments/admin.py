from decimal import Decimal
from django.contrib import admin
from django.db import transaction
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib.admin.views.decorators import staff_member_required

from .models import Transaction, CurrencySetting, Withdrawal
from .services import modify_user_balance
from users.models import has_admin_perm, Profile


def _link_user_promo_code(user, promo_code, admin_user, tx=None):
    """
    Links user to promo_code / blogger on manual deposit.
    - Commission from deposit itself is strictly 0 UC (only Net Loss generates payout).
    - If user already has a linked promo code:
      - Superuser can re-bind with explicit audit log.
      - Regular staff cannot re-bind (original code is preserved).
    """
    from cases.models import PromoCodeUse
    import logging
    audit_logger = logging.getLogger('neondrop.audit')
    sec_logger = logging.getLogger('neondrop.security')

    if not promo_code:
        return

    existing_use = PromoCodeUse.objects.filter(user=user).select_related('promo_code').order_by('-used_at').first()

    if not existing_use:
        # First time linking user to promo code on deposit
        PromoCodeUse.objects.create(
            user=user,
            promo_code=promo_code,
            bonus_amount=Decimal('0.00'),
            related_transaction=tx
        )
        audit_logger.info(f"PROMO_CODE_LINKED_ON_DEPOSIT: user={user.username} promo_code={promo_code.code} admin={admin_user.username}")
    elif existing_use.promo_code_id == promo_code.id:
        # Already linked to this exact promo code
        audit_logger.info(f"PROMO_CODE_ALREADY_LINKED: user={user.username} promo_code={promo_code.code}")
    else:
        # Re-binding attempt: user already has a different linked promo code
        if admin_user.is_superuser:
            old_code = existing_use.promo_code.code
            PromoCodeUse.objects.create(
                user=user,
                promo_code=promo_code,
                bonus_amount=Decimal('0.00'),
                related_transaction=tx
            )
            audit_logger.info(f"PROMO_CODE_REBIND: user={user.username} old={old_code} new={promo_code.code} admin={admin_user.username}")
        else:
            sec_logger.warning(
                f"PROMO_CODE_REBIND_DENIED: Staff user {admin_user.username} attempted to rebind user {user.username} "
                f"from {existing_use.promo_code.code} to {promo_code.code}. Kept original code."
            )


@admin.action(description='✅ Подтвердить выбранные заявки и начислить баланс')
def approve_deposits(modeladmin, request, queryset):
    if not has_admin_perm(request.user, 'can_approve_deposits'):
        if modeladmin:
            modeladmin.message_user(request, "⛔ Ошибка доступа: у вас нет прав на подтверждение пополнений (can_approve_deposits).", level=messages.ERROR)
        return

    approved_count = 0
    for tx in queryset.filter(status='pending'):
        try:
            with transaction.atomic():
                if tx.transaction_type == 'deposit':
                    # Directly mutate balance and complete this transaction without duplicate ledger entry
                    profile = tx.user.profile
                    tx.balance_before = profile.balance
                    profile.balance += tx.amount
                    profile.save(update_fields=['balance'])
                    tx.balance_after = profile.balance
                    tx.description = f"{tx.description or ''} (Подтверждено админом: {request.user.username})".strip()

                    # Associate user with promo code / blogger if specified
                    if tx.promo_code:
                        _link_user_promo_code(user=tx.user, promo_code=tx.promo_code, admin_user=request.user, tx=tx)
                tx.status = 'completed'
                tx.save(update_fields=['status', 'balance_before', 'balance_after', 'description', 'updated_at'])
                approved_count += 1
        except Exception as e:
            if modeladmin:
                modeladmin.message_user(request, f"Ошибка при обработке заявки #{tx.id}: {e}", level=messages.ERROR)
            
    if approved_count > 0 and modeladmin:
        modeladmin.message_user(request, f"Успешно подтверждено заявок: {approved_count}.", level=messages.SUCCESS)


@admin.action(description='❌ Отклонить выбранные заявки (с возвратом средств)')
def reject_deposits(modeladmin, request, queryset):
    if not (has_admin_perm(request.user, 'can_approve_withdrawals') or has_admin_perm(request.user, 'can_approve_deposits')):
        if modeladmin:
            modeladmin.message_user(request, "⛔ Ошибка доступа: у вас нет прав на отклонение/обработку заявок.", level=messages.ERROR)
        return

    rejected_count = 0
    for tx in queryset.filter(status='pending'):
        try:
            with transaction.atomic():
                # If withdrawal: refund reserved funds
                if 'withdraw' in tx.transaction_type.lower():
                    refund_amount = abs(tx.amount)
                    modify_user_balance(
                        user=tx.user,
                        amount_delta=refund_amount,
                        transaction_type='admin_adjustment',
                        reference_id=f"withdraw_refund:{tx.id}",
                        description=f"Возврат средств за отклоненную заявку на вывод #{tx.id}",
                        admin_user=request.user
                    )
                tx.status = 'rejected'
                tx.save(update_fields=['status', 'updated_at'])
                rejected_count += 1
        except Exception as e:
            if modeladmin:
                modeladmin.message_user(request, f"Ошибка при отклонении заявки #{tx.id}: {e}", level=messages.ERROR)

    if rejected_count > 0 and modeladmin:
        modeladmin.message_user(request, f"Отклонено заявок: {rejected_count}. Средства проверены.", level=messages.WARNING)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user_link', 'amount_badge', 'promo_code_badge', 'created_at',
        'status_badge', 'transaction_type_badge', 'payment_method', 'quick_actions'
    )
    list_filter = ('status', 'transaction_type', 'promo_code', 'payment_method', 'created_at')
    search_fields = ('user__username', 'user__email', 'promo_code__code', 'promo_code__blogger_name', 'idempotency_key', 'reference_id', 'description')
    autocomplete_fields = ('user', 'promo_code')
    readonly_fields = ('created_at', 'updated_at', 'balance_before', 'balance_after', 'ip_address')
    actions = [approve_deposits, reject_deposits]
    ordering = ('-created_at',)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return has_admin_perm(request.user, 'can_view_deposits') or has_admin_perm(request.user, 'can_view_withdrawals')

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return has_admin_perm(request.user, 'can_approve_deposits') or has_admin_perm(request.user, 'can_approve_withdrawals')

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return has_admin_perm(request.user, 'can_approve_deposits')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        can_dep = has_admin_perm(request.user, 'can_view_deposits')
        can_wdr = has_admin_perm(request.user, 'can_view_withdrawals')
        if can_dep and can_wdr:
            return qs
        if can_dep:
            return qs.exclude(transaction_type__icontains='withdraw')
        if can_wdr:
            return qs.filter(transaction_type__icontains='withdraw')
        return qs.none()

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        old_obj = Transaction.objects.filter(pk=obj.pk).first() if not is_new else None

        if obj.transaction_type == 'deposit' and obj.status == 'completed':
            was_already_completed = old_obj and old_obj.status == 'completed'
            if not was_already_completed:
                profile = obj.user.profile
                obj.balance_before = profile.balance
                profile.balance += obj.amount
                profile.save(update_fields=['balance'])
                obj.balance_after = profile.balance
                obj.description = f"{obj.description or ''} (Вручную админом: {request.user.username})".strip()
                if obj.promo_code:
                    _link_user_promo_code(user=obj.user, promo_code=obj.promo_code, admin_user=request.user, tx=obj)
        super().save_model(request, obj, form, change)
    actions = [approve_deposits, reject_deposits]
    ordering = ('-created_at',)

    def promo_code_badge(self, obj):
        if obj.promo_code:
            blogger_part = f" ({obj.promo_code.blogger_name})" if obj.promo_code.blogger_name else ""
            return format_html('<span class="badge-neon-purple" style="font-size: 11px;">🎟️ {}{}</span>', obj.promo_code.code, blogger_part)
        return format_html('<span style="color: #64748b; font-size: 12px;">—</span>')
    promo_code_badge.short_description = 'Промокод / Блогер'
    promo_code_badge.admin_order_field = 'promo_code__code'

    def user_link(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.user.id])
        return format_html('<a href="{}" style="font-weight: 700;">{}</a>', url, obj.user.username)
    user_link.short_description = 'Пользователь'
    user_link.admin_order_field = 'user__username'

    def amount_badge(self, obj):
        sign = "+" if obj.amount > 0 else ""
        color = "#34d399" if obj.amount > 0 else "#f87171"
        amt_str = f"{abs(obj.amount):.2f}"
        return format_html('<strong style="color: {}; font-size: 14px;">{}{} UC</strong>', color, sign, amt_str)
    amount_badge.short_description = 'Сумма'
    amount_badge.admin_order_field = 'amount'

    def status_badge(self, obj):
        if obj.status == 'completed':
            return format_html('<span class="badge-neon-green">✓ ЗАВЕРШЕНО</span>')
        if obj.status == 'pending':
            return format_html('<span class="badge-neon-yellow">⏳ ОЖИДАЕТ</span>')
        if obj.status == 'rejected':
            return format_html('<span class="badge-neon-red">✕ ОТКЛОНЕНО</span>')
        return format_html('<span class="badge-neon-red">ОШИБКА</span>')
    status_badge.short_description = 'Статус'
    status_badge.admin_order_field = 'status'

    def transaction_type_badge(self, obj):
        ttype = obj.get_transaction_type_display()
        if 'deposit' in obj.transaction_type:
            return format_html('<span class="badge-neon-green">{}</span>', ttype)
        if 'withdraw' in obj.transaction_type:
            return format_html('<span class="badge-neon-red">{}</span>', ttype)
        return format_html('<span class="badge-neon-purple">{}</span>', ttype)
    transaction_type_badge.short_description = 'Тип'
    transaction_type_badge.admin_order_field = 'transaction_type'

    def quick_actions(self, obj):
        if obj.status == 'pending':
            approve_url = reverse('admin:payments_tx_approve', args=[obj.id])
            reject_url = reverse('admin:payments_tx_reject', args=[obj.id])
            return format_html(
                '<div style="display: flex; gap: 6px;">'
                '<a href="{}" class="button" style="background: linear-gradient(135deg, #059669, #10b981) !important; padding: 4px 8px !important; font-size: 11px !important;">✅ Одобрить</a>'
                '<a href="{}" class="button" style="background: linear-gradient(135deg, #dc2626, #ef4444) !important; padding: 4px 8px !important; font-size: 11px !important;">❌ Отклонить</a>'
                '</div>',
                approve_url, reject_url
            )
        return format_html('<span style="color: #64748b; font-size: 12px;">Завершено</span>')
    quick_actions.short_description = 'Действия'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:tx_id>/approve/', self.admin_site.admin_view(self.approve_single_tx), name='payments_tx_approve'),
            path('<int:tx_id>/reject/', self.admin_site.admin_view(self.reject_single_tx), name='payments_tx_reject'),
        ]
        return custom_urls + urls

    def approve_single_tx(self, request, tx_id):
        if not has_admin_perm(request.user, 'can_approve_deposits'):
            messages.error(request, "⛔ Ошибка доступа: у вас нет прав на подтверждение пополнений (can_approve_deposits).")
            return redirect('admin:payments_transaction_changelist')

        tx = get_object_or_404(Transaction, id=tx_id)
        if tx.status == 'pending':
            try:
                with transaction.atomic():
                    if tx.transaction_type == 'deposit':
                        profile = tx.user.profile
                        tx.balance_before = profile.balance
                        profile.balance += tx.amount
                        profile.save(update_fields=['balance'])
                        tx.balance_after = profile.balance
                        tx.description = f"{tx.description or ''} (Подтверждено админом: {request.user.username})".strip()

                        # Associate user with promo code / blogger if specified
                        if tx.promo_code:
                            _link_user_promo_code(user=tx.user, promo_code=tx.promo_code, admin_user=request.user, tx=tx)
                    tx.status = 'completed'
                    tx.save(update_fields=['status', 'balance_before', 'balance_after', 'description', 'updated_at'])
                    messages.success(request, f"Заявка #{tx.id} успешно одобрена! Баланс пользователя пополнен.")
            except Exception as e:
                messages.error(request, f"Ошибка при одобрении заявки #{tx.id}: {e}")
        return redirect('admin:payments_transaction_changelist')

    def reject_single_tx(self, request, tx_id):
        if not (has_admin_perm(request.user, 'can_approve_withdrawals') or has_admin_perm(request.user, 'can_approve_deposits')):
            messages.error(request, "⛔ Ошибка доступа: у вас нет прав на отклонение заявок.")
            return redirect('admin:payments_transaction_changelist')

        tx = get_object_or_404(Transaction, id=tx_id)
        if tx.status == 'pending':
            try:
                with transaction.atomic():
                    if 'withdraw' in tx.transaction_type.lower():
                        refund_amount = abs(tx.amount)
                        modify_user_balance(
                            user=tx.user,
                            amount_delta=refund_amount,
                            transaction_type='admin_adjustment',
                            reference_id=f"withdraw_refund:{tx.id}",
                            description=f"Возврат средств за отклоненную заявку на вывод #{tx.id}",
                            admin_user=request.user
                        )
                    tx.status = 'rejected'
                    tx.save(update_fields=['status', 'updated_at'])
                    messages.warning(request, f"Заявка #{tx.id} отклонена. Средства проверены/возвращены.")
            except Exception as e:
                messages.error(request, f"Ошибка при отклонении заявки #{tx.id}: {e}")
        return redirect('admin:payments_transaction_changelist')

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(CurrencySetting)
class CurrencySettingAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'uc_to_uzs', 'usd_to_uzs', 'calculated_uc_in_usd', 'is_active', 'updated_at')
    list_editable = ('uc_to_uzs', 'usd_to_uzs', 'is_active')
    
    def calculated_uc_in_usd(self, obj):
        if obj.usd_to_uzs > 0:
            rate = obj.uc_to_uzs / obj.usd_to_uzs
            return f"1 UC ≈ ${rate:.4f} USD (60 UC ≈ ${(60 * rate):.2f})"
        return "N/A"
    calculated_uc_in_usd.short_description = "Расчёт стоимости 1 UC"


@admin.action(description='✅ Одобрить выбранные заявки на вывод (списать UC)')
def approve_withdrawals_action(modeladmin, request, queryset):
    if not has_admin_perm(request.user, 'can_approve_withdrawals'):
        modeladmin.message_user(request, "⛔ Ошибка доступа: у вас нет прав на подтверждение выводов (can_approve_withdrawals).", level=messages.ERROR)
        return

    approved_count = 0
    for w in queryset.filter(status='pending'):
        try:
            with transaction.atomic():
                profile = Profile.objects.select_for_update().get(user=w.user)
                if profile.balance < w.amount:
                    modeladmin.message_user(
                        request,
                        f"Недостаточно средств у пользователя {w.username} (Баланс: {profile.balance} UC, требуется: {w.amount} UC). Заявка #{w.id} не одобрена.",
                        level=messages.ERROR
                    )
                    continue

                # Deduct balance strictly once
                balance_before = profile.balance
                profile.balance -= w.amount
                profile.save(update_fields=['balance'])
                balance_after = profile.balance

                # Record authoritative Transaction ledger entry
                tx = Transaction.objects.create(
                    user=w.user,
                    amount=-w.amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    transaction_type='withdraw',
                    status='completed',
                    payment_method='telegram',
                    reference_id=f"withdrawal:{w.id}",
                    description=f"Вывод средств #{w.id} ({w.method}: {w.details}) (Одобрено админом: {request.user.username})",
                    comment=w.details
                )

                w.status = 'approved'
                w.processed_by = request.user
                w.related_transaction = tx
                w.save(update_fields=['status', 'processed_by', 'related_transaction', 'updated_at'])
                approved_count += 1
        except Exception as e:
            modeladmin.message_user(request, f"Ошибка при обработке заявки #{w.id}: {e}", level=messages.ERROR)

    if approved_count > 0:
        modeladmin.message_user(request, f"Успешно одобрено заявок на вывод: {approved_count}.", level=messages.SUCCESS)


@admin.action(description='❌ Отклонить выбранные заявки на вывод (баланс не изменяется)')
def reject_withdrawals_action(modeladmin, request, queryset):
    if not has_admin_perm(request.user, 'can_approve_withdrawals'):
        modeladmin.message_user(request, "⛔ Ошибка доступа: у вас нет прав на отклонение выводов.", level=messages.ERROR)
        return

    rejected_count = 0
    for w in queryset.filter(status='pending'):
        try:
            with transaction.atomic():
                w.status = 'rejected'
                w.processed_by = request.user
                w.save(update_fields=['status', 'processed_by', 'updated_at'])
                rejected_count += 1
        except Exception as e:
            modeladmin.message_user(request, f"Ошибка при отклонении заявки #{w.id}: {e}", level=messages.ERROR)

    if rejected_count > 0:
        modeladmin.message_user(request, f"Отклонено заявок на вывод: {rejected_count}. Баланс пользователей не изменялся.", level=messages.WARNING)


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'username_display', 'user_id_display', 'amount_badge',
        'method', 'details_display', 'created_at', 'status_badge', 'quick_actions'
    )
    list_filter = ('status', 'method', 'created_at')
    search_fields = ('username', 'user__email', 'user__id', 'details', 'method', 'id')
    readonly_fields = ('created_at', 'updated_at', 'username', 'user_id_val', 'processed_by', 'related_transaction')
    actions = [approve_withdrawals_action, reject_withdrawals_action]
    ordering = ('-created_at',)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return has_admin_perm(request.user, 'can_view_withdrawals')

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return has_admin_perm(request.user, 'can_approve_withdrawals')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def username_display(self, obj):
        url = reverse('admin:auth_user_change', args=[obj.user.id])
        return format_html('<a href="{}" style="font-weight: 700; color: #a855f7;">👤 {}</a>', url, obj.username)
    username_display.short_description = 'Пользователь'
    username_display.admin_order_field = 'username'

    def user_id_display(self, obj):
        return format_html('<span style="font-family: monospace; color: #94a3b8;">#{}</span>', obj.user_id_val)
    user_id_display.short_description = 'User ID'
    user_id_display.admin_order_field = 'user_id_val'

    def amount_badge(self, obj):
        return format_html('<strong style="color: #ec4899; font-size: 14px;">-{} UC</strong>', f"{obj.amount:.2f}")
    amount_badge.short_description = 'Сумма'
    amount_badge.admin_order_field = 'amount'

    def details_display(self, obj):
        text = obj.details or ""
        short = (text[:45] + '...') if len(text) > 45 else text
        return format_html('<span title="{}">{}</span>', text, short)
    details_display.short_description = 'Реквизиты'

    def status_badge(self, obj):
        if obj.status in ('approved', 'completed'):
            return format_html('<span class="badge-neon-green">✓ ОДОБРЕНО</span>')
        if obj.status == 'pending':
            return format_html('<span class="badge-neon-yellow">⏳ ОЖИДАЕТ</span>')
        if obj.status == 'rejected':
            return format_html('<span class="badge-neon-red">✕ ОТКЛОНЕНО</span>')
        return format_html('<span class="badge-neon-purple">{}</span>', obj.get_status_display())
    status_badge.short_description = 'Статус'
    status_badge.admin_order_field = 'status'

    def quick_actions(self, obj):
        if obj.status == 'pending':
            approve_url = reverse('admin:payments_withdrawal_approve', args=[obj.id])
            reject_url = reverse('admin:payments_withdrawal_reject', args=[obj.id])
            return format_html(
                '<div style="display: flex; gap: 6px;">'
                '<a href="{}" onclick="return confirm(\'Вы действительно хотите ОДОБРИТЬ вывод #{} на сумму {} UC для пользователя {}? Баланс будет списан.\');" '
                'class="button" style="background: linear-gradient(135deg, #059669, #10b981) !important; padding: 4px 8px !important; font-size: 11px !important;">✅ Одобрить</a>'
                '<a href="{}" onclick="return confirm(\'Отклонить заявку на вывод #{}?\');" '
                'class="button" style="background: linear-gradient(135deg, #dc2626, #ef4444) !important; padding: 4px 8px !important; font-size: 11px !important;">❌ Отклонить</a>'
                '</div>',
                approve_url, obj.id, obj.amount, obj.username,
                reject_url, obj.id
            )
        if obj.status in ('approved', 'completed'):
            return format_html('<span style="color: #10b981; font-weight: 600; font-size: 12px;">Выплачено</span>')
        return format_html('<span style="color: #64748b; font-size: 12px;">Отклонено</span>')
    quick_actions.short_description = 'Действия'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:withdrawal_id>/approve/', self.admin_site.admin_view(self.approve_single_withdrawal), name='payments_withdrawal_approve'),
            path('<int:withdrawal_id>/reject/', self.admin_site.admin_view(self.reject_single_withdrawal), name='payments_withdrawal_reject'),
        ]
        return custom_urls + urls

    def approve_single_withdrawal(self, request, withdrawal_id):
        if not has_admin_perm(request.user, 'can_approve_withdrawals'):
            messages.error(request, "⛔ Ошибка доступа: у вас нет прав на подтверждение выводов (can_approve_withdrawals).")
            return redirect('admin:payments_withdrawal_changelist')

        w = get_object_or_404(Withdrawal, id=withdrawal_id)
        if w.status != 'pending':
            messages.warning(request, f"Заявка #{w.id} уже обработана (текущий статус: {w.get_status_display()}). Повторное действие невозможно.")
            return redirect('admin:payments_withdrawal_changelist')

        try:
            with transaction.atomic():
                profile = Profile.objects.select_for_update().get(user=w.user)
                if profile.balance < w.amount:
                    messages.error(
                        request,
                        f"Недостаточно средств у пользователя {w.username}! Баланс: {profile.balance} UC, сумма вывода: {w.amount} UC. Списание отменено."
                    )
                    return redirect('admin:payments_withdrawal_changelist')

                balance_before = profile.balance
                profile.balance -= w.amount
                profile.save(update_fields=['balance'])
                balance_after = profile.balance

                tx = Transaction.objects.create(
                    user=w.user,
                    amount=-w.amount,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    transaction_type='withdraw',
                    status='completed',
                    payment_method='telegram',
                    reference_id=f"withdrawal:{w.id}",
                    description=f"Вывод средств #{w.id} ({w.method}: {w.details}) (Одобрено админом: {request.user.username})",
                    comment=w.details
                )

                w.status = 'approved'
                w.processed_by = request.user
                w.related_transaction = tx
                w.save(update_fields=['status', 'processed_by', 'related_transaction', 'updated_at'])
                messages.success(request, f"Заявка #{w.id} успешно одобрена! С баланса пользователя {w.username} списано {w.amount} UC.")
        except Exception as e:
            messages.error(request, f"Ошибка при одобрении заявки #{w.id}: {e}")

        return redirect('admin:payments_withdrawal_changelist')

    def reject_single_withdrawal(self, request, withdrawal_id):
        if not has_admin_perm(request.user, 'can_approve_withdrawals'):
            messages.error(request, "⛔ Ошибка доступа: у вас нет прав на отклонение выводов.")
            return redirect('admin:payments_withdrawal_changelist')

        w = get_object_or_404(Withdrawal, id=withdrawal_id)
        if w.status != 'pending':
            messages.warning(request, f"Заявка #{w.id} уже обработана (текущий статус: {w.get_status_display()}).")
            return redirect('admin:payments_withdrawal_changelist')

        try:
            with transaction.atomic():
                w.status = 'rejected'
                w.processed_by = request.user
                w.save(update_fields=['status', 'processed_by', 'updated_at'])
                messages.warning(request, f"Заявка #{w.id} отклонена. Баланс пользователя не изменялся.")
        except Exception as e:
            messages.error(request, f"Ошибка при отклонении заявки #{w.id}: {e}")

        return redirect('admin:payments_withdrawal_changelist')

