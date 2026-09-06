from django.contrib import admin
from .models import Contract, ContractInputItem

class ContractInputItemInline(admin.TabularInline):
    model = ContractInputItem
    extra = 0
    readonly_fields = ('item',)

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'items_count', 'total_input_value', 'reward_item', 'get_reward_value', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'reward_item__name')
    inlines = [ContractInputItemInline]
    ordering = ('-created_at',)

    def get_reward_value(self, obj):
        return f"{obj.reward_item.value} UC"
    get_reward_value.short_description = 'Стоимость награды'
