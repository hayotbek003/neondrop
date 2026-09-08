from decimal import Decimal
from django.contrib import admin
from django.db import transaction
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.contrib.admin.views.decorators import staff_member_required

from .models import Transaction, CurrencySetting
from .services import modify_user_balance


@admin.action(description='✅ Подтвердить выбранные заявки и начислить баланс')
def approve_deposits(modeladmin, request, queryset):
    from cases.models import PromoCodeUse
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
                        PromoCodeUse.objects.get_or_create(
                            user=tx.user,
                            promo_code=tx.promo_code,
                            defaults={
                                'bonus_amount': Decimal('0.00'),
                                'related_transaction': tx,
                            }
                        )
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
        from cases.models import PromoCodeUse
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
                            PromoCodeUse.objects.get_or_create(
                                user=tx.user,
                                promo_code=tx.promo_code,
                                defaults={
                                    'bonus_amount': Decimal('0.00'),
                                    'related_transaction': tx,
                                }
                            )
                    tx.status = 'completed'
                    tx.save(update_fields=['status', 'balance_before', 'balance_after', 'description', 'updated_at'])
                    messages.success(request, f"Заявка #{tx.id} успешно одобрена! Баланс пользователя пополнен.")
            except Exception as e:
                messages.error(request, f"Ошибка при одобрении заявки #{tx.id}: {e}")
        return redirect('admin:payments_transaction_changelist')

    def reject_single_tx(self, request, tx_id):
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
