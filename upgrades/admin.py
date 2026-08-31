from django.contrib import admin
from .models import UpgradeAttempt

@admin.register(UpgradeAttempt)
class UpgradeAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'source_item', 'target_item', 'chance', 'roll', 'is_success', 'created_at')
    list_filter = ('is_success', 'created_at')
    search_fields = ('user__username', 'source_item__name', 'target_item__name')
    ordering = ('-created_at',)
