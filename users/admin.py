from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import Profile, GoogleAccount

class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Профиль'
    fk_name = 'user'

class GoogleAccountInline(admin.StackedInline):
    model = GoogleAccount
    can_delete = True
    extra = 0
    verbose_name_plural = 'Привязанный Google аккаунт'
    readonly_fields = ('google_id', 'email', 'created_at', 'updated_at')

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline, GoogleAccountInline)
    list_display = ('username', 'email', 'get_balance', 'has_google', 'is_staff', 'date_joined')
    
    def get_balance(self, instance):
        if hasattr(instance, 'profile') and instance.profile:
            return f"${instance.profile.balance:.2f}"
        return "$0.00"
    get_balance.short_description = 'Баланс'

    def has_google(self, instance):
        return hasattr(instance, 'google_account')
    has_google.boolean = True
    has_google.short_description = 'Google'

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'telegram_username', 'total_opened', 'total_winnings', 'created_at')
    search_fields = ('user__username', 'user__email', 'telegram_username')
    list_filter = ('created_at',)
    ordering = ('-created_at',)

@admin.register(GoogleAccount)
class GoogleAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'email', 'google_id', 'created_at')
    search_fields = ('user__username', 'user__email', 'email', 'google_id')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

