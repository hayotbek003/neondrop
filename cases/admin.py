from django.contrib import admin
from .models import Category, Item, Case, CaseItem, Opening

class CaseItemInline(admin.TabularInline):
    model = CaseItem
    extra = 1
    autocomplete_fields = ('item',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('order', 'name')

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'weapon_type', 'skin_name', 'value', 'rarity', 'created_at')
    list_filter = ('rarity', 'weapon_type', 'created_at')
    search_fields = ('name', 'weapon_type', 'skin_name')
    ordering = ('-value',)

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'category', 'color_theme', 'is_popular', 'is_new', 'active', 'order')
    list_filter = ('active', 'is_popular', 'is_new', 'color_theme', 'category')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [CaseItemInline]
    ordering = ('order', 'price')

@admin.register(CaseItem)
class CaseItemAdmin(admin.ModelAdmin):
    list_display = ('case', 'item', 'weight')
    list_filter = ('case', 'item__rarity')
    search_fields = ('case__name', 'item__name')
    autocomplete_fields = ('case', 'item')

@admin.register(Opening)
class OpeningAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'case', 'item', 'price', 'created_at')
    list_filter = ('case', 'item__rarity', 'created_at')
    search_fields = ('user__username', 'item__name', 'case__name', 'server_seed_hash')
    ordering = ('-created_at',)
    readonly_fields = ('server_seed_hash', 'server_seed', 'client_seed', 'nonce', 'created_at')
