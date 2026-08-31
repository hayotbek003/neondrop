from django.contrib import admin
from django.db import transaction
from django.contrib import messages
from .models import Transaction
from .services import modify_user_balance

@admin.action(description='✅ Подтвердить выбранные заявки и начислить баланс')
def approve_deposits(modeladmin, request, queryset):
    approved_count = 0
    for tx in queryset.filter(status='pending'):
        try:
            with transaction.atomic():
                # Credit balance using authoritative service
                ledger_tx = modify_user_balance(
                    user=tx.user,
                    amount_delta=tx.amount,
                    transaction_type='deposit',
                    reference_id=f"deposit_approved:{tx.id}",
                    description=f"Подтверждение пополнения через Telegram (Заявка #{tx.id})",
                    payment_method=tx.payment_method,
                    ip_address='admin_panel',
                    admin_user=request.user
                )
                tx.status = 'completed'
                tx.balance_before = ledger_tx.balance_before
                tx.balance_after = ledger_tx.balance_after
                tx.save(update_fields=['status', 'balance_before', 'balance_after', 'updated_at'])
                approved_count += 1
        except Exception as e:
            if modeladmin:
                modeladmin.message_user(request, f"Ошибка при начислении заявки #{tx.id}: {e}", level=messages.ERROR)
            
    if approved_count > 0 and modeladmin:
        modeladmin.message_user(request, f"Успешно подтверждено заявок: {approved_count}. Баланс пользователей пополнен.", level=messages.SUCCESS)

@admin.action(description='❌ Отклонить выбранные заявки')
def reject_deposits(modeladmin, request, queryset):
    updated = queryset.filter(status='pending').update(status='rejected')
    if modeladmin:
        modeladmin.message_user(request, f"Отклонено заявок: {updated}.", level=messages.WARNING)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'balance_before', 'balance_after', 'transaction_type', 'status', 'payment_method', 'created_at')
    list_filter = ('transaction_type', 'status', 'payment_method', 'created_at')
    search_fields = ('user__username', 'user__email', 'idempotency_key', 'reference_id', 'description')
    readonly_fields = ('created_at', 'updated_at', 'balance_before', 'balance_after', 'ip_address')
    actions = [approve_deposits, reject_deposits]
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of financial ledger records except by superusers
        return request.user.is_superuser
