from decimal import Decimal
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html

from .models import Profile, GoogleAccount, AdminPermissionProfile, has_admin_perm
from inventory.models import InventoryItem
from cases.models import Opening, PromoCodeUse
from payments.models import Transaction


class AdminPermissionProfileInline(admin.StackedInline):
    model = AdminPermissionProfile
    can_delete = False
    extra = 0
    verbose_name_plural = '👑 Права администратора (Cyberpunk Access)'
    classes = ('collapse',)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Профиль пользователя'
    fk_name = 'user'
    fields = (
        'balance', 'telegram_username', 'avatar', 'avatar_url',
        'total_opened', 'total_winnings', 'created_at'
    )
    readonly_fields = ('created_at',)


class GoogleAccountInline(admin.StackedInline):
    model = GoogleAccount
    can_delete = True
    extra = 0
    verbose_name_plural = 'Привязанный Google аккаунт'
    readonly_fields = ('google_id', 'email', 'created_at', 'updated_at')


class UserInventoryInline(admin.TabularInline):
    model = InventoryItem
    extra = 0
    can_delete = False
    verbose_name = "Предмет в инвентаре"
    verbose_name_plural = "Инвентарь пользователя (последние предметы)"
    fields = ('item', 'item_value', 'is_sold', 'sold_price', 'source', 'created_at')
    readonly_fields = ('item', 'item_value', 'is_sold', 'sold_price', 'source', 'created_at')
    ordering = ('-created_at',)

    def item_value(self, obj):
        if obj.item:
            return format_html('<strong style="color: #fbbf24;">{} UC</strong>', obj.item.value)
        return "—"
    item_value.short_description = "Стоимость"

    def has_add_permission(self, request, obj=None):
        return False


class UserOpeningInline(admin.TabularInline):
    model = Opening
    extra = 0
    can_delete = False
    verbose_name = "Открытие кейса"
    verbose_name_plural = "История открытий кейсов (последние)"
    fields = ('case', 'item', 'item_value', 'price', 'created_at')
    readonly_fields = ('case', 'item', 'item_value', 'price', 'created_at')
    ordering = ('-created_at',)

    def item_value(self, obj):
        if obj.item:
            return format_html('<strong style="color: #34d399;">{} UC</strong>', obj.item.value)
        return "—"
    item_value.short_description = "Выигрыш"

    def has_add_permission(self, request, obj=None):
        return False


class UserTransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    can_delete = False
    verbose_name = "Транзакция"
    verbose_name_plural = "Финансовые транзакции (Ledger)"
    fields = ('amount', 'transaction_type', 'status', 'payment_method', 'balance_before', 'balance_after', 'created_at')
    readonly_fields = ('amount', 'transaction_type', 'status', 'payment_method', 'balance_before', 'balance_after', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request, obj=None):
        return False


class UserPromoCodeUseInline(admin.TabularInline):
    model = PromoCodeUse
    extra = 0
    can_delete = False
    verbose_name = "Использованный промокод"
    verbose_name_plural = "Активированные промокоды"
    fields = ('promo_code', 'bonus_amount', 'used_at')
    readonly_fields = ('promo_code', 'bonus_amount', 'used_at')
    ordering = ('-used_at',)

    def has_add_permission(self, request, obj=None):
        return False


class UserAdmin(BaseUserAdmin):
    inlines = (
        AdminPermissionProfileInline,
        ProfileInline,
        GoogleAccountInline,
        UserInventoryInline,
        UserOpeningInline,
        UserTransactionInline,
        UserPromoCodeUseInline,
    )
    list_display = (
        'id', 'username', 'email', 'get_balance', 'get_inventory_count',
        'get_openings_count', 'status_badge', 'has_google', 'date_joined'
    )
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'profile__telegram_username')
    ordering = ('-date_joined',)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return has_admin_perm(request.user, 'can_view_users')

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        # Staff users cannot edit superuser accounts!
        if obj and obj.is_superuser:
            return False
        return has_admin_perm(request.user, 'can_edit_users')

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_balance(self, instance):
        if hasattr(instance, 'profile') and instance.profile:
            return format_html('<strong style="color: #38bdf8; font-size: 14px;">{} UC</strong>', instance.profile.balance)
        return "0.00 UC"
    get_balance.short_description = 'Баланс'
    get_balance.admin_order_field = 'profile__balance'

    def get_inventory_count(self, instance):
        count = instance.inventory_items.filter(is_sold=False).count()
        return format_html('<span class="badge-neon-purple">{} шт.</span>', count)
    get_inventory_count.short_description = 'Инвентарь'

    def get_openings_count(self, instance):
        count = instance.openings.count()
        return format_html('<span class="badge-neon-yellow">{} кейсов</span>', count)
    get_openings_count.short_description = 'Открытий'

    def status_badge(self, instance):
        if instance.is_superuser:
            return format_html('<span class="badge-neon-purple">SUPERUSER</span>')
        if instance.is_staff:
            return format_html('<span class="badge-neon-cyan">STAFF</span>')
        if instance.is_active:
            return format_html('<span class="badge-neon-green">ACTIVE</span>')
        return format_html('<span class="badge-neon-red">BLOCKED</span>')
    status_badge.short_description = 'Статус'

    def has_google(self, instance):
        return hasattr(instance, 'google_account')
    has_google.boolean = True
    has_google.short_description = 'Google'


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance_display', 'telegram_username', 'total_opened', 'total_winnings', 'created_at')
    search_fields = ('user__username', 'user__email', 'telegram_username')
    list_filter = ('created_at',)
    ordering = ('-created_at',)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return has_admin_perm(request.user, 'can_view_users')

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if obj and obj.user and obj.user.is_superuser:
            return False
        return has_admin_perm(request.user, 'can_edit_users')

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def balance_display(self, obj):
        return format_html('<strong style="color: #34d399; font-size: 14px;">{} UC</strong>', obj.balance)
    balance_display.short_description = 'Баланс'


@admin.register(GoogleAccount)
class GoogleAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'email', 'google_id', 'created_at')
    search_fields = ('user__username', 'user__email', 'email', 'google_id')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
