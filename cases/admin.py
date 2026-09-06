from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Category, Item, Case, CaseItem, Opening,
    PersonalCaseChance, PromoCode, PromoCodeUse, UserFreeOpening
)

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
    list_display = ('image_preview', 'name', 'weapon_type', 'skin_name', 'value', 'rarity', 'created_at')
    list_filter = ('rarity', 'weapon_type', 'created_at')
    search_fields = ('name', 'weapon_type', 'skin_name')
    ordering = ('-value',)
    readonly_fields = ('image_preview', 'created_at')

    def image_preview(self, obj):
        if obj.display_image:
            return format_html('<img src="{}" style="width: 46px; height: 34px; object-fit: contain; border-radius: 4px; background: #0f172a; border: 1px solid #334155;" />', obj.display_image)
        return format_html('<span style="color: #64748b; font-size: 11px;">SVG ID</span>')
    image_preview.short_description = "Превью"

@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('image_preview', 'name', 'price', 'category', 'color_theme', 'is_popular', 'is_new', 'active', 'order')
    list_filter = ('active', 'is_popular', 'is_new', 'color_theme', 'category')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [CaseItemInline]
    ordering = ('order', 'price')
    readonly_fields = ('image_preview', 'created_at')

    def image_preview(self, obj):
        if obj.display_image:
            return format_html('<img src="{}" style="width: 50px; height: 38px; object-fit: contain; border-radius: 6px; background: #0f172a; border: 1px solid #334155;" />', obj.display_image)
        return format_html('<span style="color: #64748b; font-size: 11px;">(Тема: {})</span>', obj.color_theme)
    image_preview.short_description = "Фото кейса"

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

@admin.register(PersonalCaseChance)
class PersonalCaseChanceAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'case', 'item', 'chance_display', 'normal_chance_display',
        'status_badge', 'starts_at', 'expires_at'
    )
    list_filter = ('is_active', 'case', 'starts_at', 'expires_at')
    search_fields = ('user__username', 'case__name', 'item__name')
    autocomplete_fields = ('user', 'case', 'item')
    ordering = ('-created_at',)

    @admin.display(description="Персональный шанс")
    def chance_display(self, obj):
        return format_html('<strong style="color: #ffd700; font-size: 13px;">{}%</strong>', obj.chance)

    @admin.display(description="Обычный шанс")
    def normal_chance_display(self, obj):
        return f"{obj.normal_chance_percent()}%"

    @admin.display(description="Статус")
    def status_badge(self, obj):
        now = timezone.now()
        if not obj.is_active:
            return format_html('<span style="color: #94a3b8; font-weight: bold;">✕ Выключен</span>')
        if obj.expires_at < now:
            return format_html('<span style="color: #ef4444; font-weight: bold;">✕ Истёк</span>')
        if obj.starts_at > now:
            return format_html('<span style="color: #eab308; font-weight: bold;">⏳ Ожидает начала</span>')
        return format_html('<span style="color: #22c55e; font-weight: bold;">✓ Активен</span>')

@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'bonus_type_display', 'bonus_value', 'usage_display',
        'status_badge', 'starts_at', 'expires_at'
    )
    list_filter = ('is_active', 'bonus_type', 'starts_at', 'expires_at')
    search_fields = ('code',)
    autocomplete_fields = ('case',)
    ordering = ('-created_at',)

    @admin.display(description="Тип бонуса")
    def bonus_type_display(self, obj):
        return obj.get_bonus_type_display()

    @admin.display(description="Использовано / Лимит")
    def usage_display(self, obj):
        pct = int(round((obj.used_count / obj.max_uses) * 100)) if obj.max_uses > 0 else 0
        color = '#22c55e' if pct < 80 else '#ef4444'
        return format_html(
            '<strong>{} / {}</strong> <span style="color: {}; font-size: 11px;">({}%)</span>',
            obj.used_count, obj.max_uses, color, pct
        )

    @admin.display(description="Статус")
    def status_badge(self, obj):
        now = timezone.now()
        if not obj.is_active:
            return format_html('<span style="color: #94a3b8; font-weight: bold;">✕ Выключен</span>')
        if obj.used_count >= obj.max_uses:
            return format_html('<span style="color: #ef4444; font-weight: bold;">✕ Лимит исчерпан</span>')
        if obj.expires_at < now:
            return format_html('<span style="color: #ef4444; font-weight: bold;">✕ Истёк</span>')
        if obj.starts_at > now:
            return format_html('<span style="color: #eab308; font-weight: bold;">⏳ Ожидает начала</span>')
        return format_html('<span style="color: #22c55e; font-weight: bold;">✓ Активен</span>')

@admin.register(PromoCodeUse)
class PromoCodeUseAdmin(admin.ModelAdmin):
    list_display = ('user', 'promo_code', 'bonus_amount', 'used_at', 'related_transaction')
    list_filter = ('promo_code__bonus_type', 'used_at')
    search_fields = ('user__username', 'promo_code__code')
    readonly_fields = ('user', 'promo_code', 'used_at', 'bonus_amount', 'related_transaction')
    ordering = ('-used_at',)

@admin.register(UserFreeOpening)
class UserFreeOpeningAdmin(admin.ModelAdmin):
    list_display = ('user', 'case', 'openings_left', 'total_granted', 'promo_code', 'updated_at')
    list_filter = ('case', 'updated_at')
    search_fields = ('user__username', 'case__name', 'promo_code__code')
    autocomplete_fields = ('user', 'case', 'promo_code')
    ordering = ('-updated_at',)
