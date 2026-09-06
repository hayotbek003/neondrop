from django.contrib import admin
from .models import InventoryItem

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'get_value', 'source', 'is_sold', 'sold_price', 'created_at')
    list_filter = ('is_sold', 'source', 'created_at', 'item__rarity')
    search_fields = ('user__username', 'item__name', 'item__weapon_type', 'item__skin_name')
    ordering = ('-created_at',)
    autocomplete_fields = ('user', 'item', 'opening')

    def get_value(self, obj):
        return f"{obj.item.value} UC"
    get_value.short_description = 'Стоимость'
