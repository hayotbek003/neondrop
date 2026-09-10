from decimal import Decimal
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from users.models import has_admin_perm
from .models import (
    Category, Item, Case, CaseItem, Opening,
    PersonalCaseChance, PromoCode, PromoCodeUse, UserFreeOpening,
    BloggerPayout
)

class CaseItemInline(admin.TabularInline):
    model = CaseItem
    extra = 1
    autocomplete_fields = ('item',)
    fields = ('item', 'item_preview', 'item_price', 'item_rarity', 'weight', 'calculated_chance')
    readonly_fields = ('item_preview', 'item_price', 'item_rarity', 'calculated_chance')
    ordering = ('-weight',)

    def has_change_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_case_chances')

    def has_add_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_case_chances')

    def has_delete_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_case_chances')

    def item_preview(self, obj):
        if obj.item_id and obj.item.display_image:
            return format_html('<img src="{}" style="width: 42px; height: 32px; object-fit: contain; border-radius: 4px; background: #0f172a; border: 1px solid #334155;" />', obj.item.display_image)
        return "—"
    item_preview.short_description = "Превью"

    def item_price(self, obj):
        if obj.item_id:
            return format_html('<strong style="color: #fbbf24; font-size: 13px;">{} UC</strong>', obj.item.value)
        return "—"
    item_price.short_description = "Цена (UC)"

    def item_rarity(self, obj):
        if obj.item_id:
            color = obj.item.rarity_color or '#4B69FF'
            return format_html(
                '<span style="border: 1px solid {}; color: {}; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
                color, color, obj.item.get_rarity_display()
            )
        return "—"
    item_rarity.short_description = "Редкость"

    def calculated_chance(self, obj):
        if obj.case_id and obj.weight:
            total_w = sum(ci.weight for ci in obj.case.case_items.all())
            if total_w > 0:
                pct = (obj.weight / total_w) * 100.0
                return format_html('<strong style="color: #38bdf8; font-size: 13px;">{:.3f}%</strong>', pct)
        return "—"
    calculated_chance.short_description = "Шанс (%)"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('order', 'name')

    def has_view_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_view_cases')

    def has_add_permission(self, request):
        return has_admin_perm(request.user, 'can_add_cases')

    def has_change_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_cases')

    def has_delete_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_delete_cases')


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('image_preview', 'name', 'game_badge', 'item_type', 'weapon_type', 'value_display', 'rarity_badge', 'related_cases_display', 'created_at')
    list_editable = ('value_display_edit',) if False else ()
    list_filter = ('game', 'rarity', 'item_type', 'weapon_type', 'created_at')
    search_fields = ('name', 'weapon_type', 'skin_name', 'source_id', 'source_url')
    ordering = ('-value',)
    readonly_fields = ('image_preview', 'created_at', 'containing_cases_display')

    def game_badge(self, obj):
        return format_html('<span style="background: rgba(245, 158, 11, 0.15); border: 1px solid #f59e0b; color: #fbbf24; padding: 2px 6px; border-radius: 4px; font-weight: 800; font-size: 10px;">{}</span>', obj.game or 'PUBG')
    game_badge.short_description = "Игра"

    def has_view_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_view_cases') or request.user.is_staff

    def has_add_permission(self, request):
        return has_admin_perm(request.user, 'can_add_items')

    def has_change_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_prices') or has_admin_perm(request.user, 'can_edit_images')

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            if not has_admin_perm(request.user, 'can_edit_prices'):
                ro.append('value')
            if not has_admin_perm(request.user, 'can_edit_images'):
                ro.extend(['image', 'image_url'])
        return ro

    def image_preview(self, obj):
        if obj.display_image:
            return format_html('<img src="{}" style="width: 48px; height: 36px; object-fit: contain; border-radius: 4px; background: #0f172a; border: 1px solid #334155;" />', obj.display_image)
        return format_html('<span style="color: #64748b; font-size: 11px;">SVG ID</span>')
    image_preview.short_description = "Превью"

    def value_display(self, obj):
        return format_html('<strong style="color: #fbbf24; font-size: 14px;">{} UC</strong>', obj.value)
    value_display.short_description = "Цена"
    value_display.admin_order_field = 'value'

    def rarity_badge(self, obj):
        color = obj.rarity_color or '#4B69FF'
        return format_html(
            '<span style="border: 1px solid {}; color: {}; padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 11px;">{}</span>',
            color, color, obj.get_rarity_display()
        )
    rarity_badge.short_description = "Редкость"
    rarity_badge.admin_order_field = 'rarity'

    def related_cases_display(self, obj):
        case_items = list(obj.case_containments.select_related('case').all()[:4])
        total = obj.case_containments.count()
        if not case_items:
            return format_html('<span style="color: #64748b; font-size: 12px;">Не в кейсах</span>')
        badges = [f'<span class="badge-neon-purple">{ci.case.name}</span>' for ci in case_items]
        if total > 4:
            badges.append(f'<span style="color: #94a3b8; font-size: 11px;">+{total - 4}</span>')
        return format_html(' '.join(badges))
    related_cases_display.short_description = "В кейсах"

    def containing_cases_display(self, obj):
        cases = [ci.case.name for ci in obj.case_containments.select_related('case').all()]
        return ", ".join(cases) if cases else "Не входит ни в один кейс"
    containing_cases_display.short_description = "Список всех связанных кейсов"


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('image_preview', 'name', 'price_display', 'category', 'color_theme_badge', 'items_count_badge', 'active', 'is_popular', 'is_new', 'order')
    list_editable = ('active', 'is_popular', 'is_new', 'order')
    list_filter = ('active', 'is_popular', 'is_new', 'color_theme', 'category')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [CaseItemInline]
    ordering = ('order', 'price')
    readonly_fields = ('image_preview', 'created_at', 'total_items_in_case', 'total_openings_count')

    def has_view_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_view_cases')

    def has_add_permission(self, request):
        return has_admin_perm(request.user, 'can_add_cases')

    def has_change_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_cases')

    def has_delete_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_delete_cases')

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            if not has_admin_perm(request.user, 'can_edit_prices'):
                ro.append('price')
            if not has_admin_perm(request.user, 'can_edit_images'):
                ro.append('image')
        return ro

    def image_preview(self, obj):
        if obj.display_image:
            return format_html('<img src="{}" style="width: 52px; height: 38px; object-fit: contain; border-radius: 6px; background: #0f172a; border: 1px solid #334155;" />', obj.display_image)
        return format_html('<span style="color: #64748b; font-size: 11px;">(Тема: {})</span>', obj.color_theme)
    image_preview.short_description = "Фото кейса"

    def price_display(self, obj):
        return format_html('<strong style="color: #fbbf24; font-size: 14px;">{} UC</strong>', obj.price)
    price_display.short_description = "Цена"
    price_display.admin_order_field = 'price'

    def color_theme_badge(self, obj):
        accent = obj.accent_color
        return format_html(
            '<span style="border-left: 3px solid {}; padding-left: 6px; font-weight: 700;">{}</span>',
            accent, obj.get_color_theme_display()
        )
    color_theme_badge.short_description = "Тема"

    def items_count_badge(self, obj):
        count = obj.case_items.count()
        return format_html('<span class="badge-neon-cyan">{} скинов</span>', count)
    items_count_badge.short_description = "Содержимое"

    def total_items_in_case(self, obj):
        return f"{obj.case_items.count()} предметов"
    total_items_in_case.short_description = "Всего предметов внутри"

    def total_openings_count(self, obj):
        return f"{obj.openings.count()} раз открыт"
    total_openings_count.short_description = "Всего открытий кейса"


@admin.register(CaseItem)
class CaseItemAdmin(admin.ModelAdmin):
    list_display = ('case', 'item', 'item_price_display', 'weight', 'chance_percent_display')
    list_filter = ('case', 'item__rarity')
    search_fields = ('case__name', 'item__name')
    autocomplete_fields = ('case', 'item')
    ordering = ('case', '-weight')

    def has_view_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_view_cases')

    def has_change_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_case_chances')

    def has_add_permission(self, request):
        return has_admin_perm(request.user, 'can_edit_case_chances')

    def has_delete_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_case_chances')

    def item_price_display(self, obj):
        return format_html('<strong style="color: #fbbf24;">{} UC</strong>', obj.item.value)
    item_price_display.short_description = "Цена скина"

    def chance_percent_display(self, obj):
        total_w = sum(ci.weight for ci in obj.case.case_items.all())
        if total_w > 0:
            pct = (obj.weight / total_w) * 100.0
            return format_html('<strong style="color: #38bdf8;">{:.3f}%</strong>', pct)
        return "0.000%"
    chance_percent_display.short_description = "Шанс (%)"

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

    def has_view_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_case_chances') or has_admin_perm(request.user, 'can_view_cases')

    def has_change_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_case_chances')

    def has_add_permission(self, request):
        return has_admin_perm(request.user, 'can_edit_case_chances')

    def has_delete_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_edit_case_chances')

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
        'code',
        'blogger_percentage_display',
        'users_count_display',
        'loss_today_display',
        'payout_today_display',
        'site_revenue_today_display',
        'loss_all_time_display',
        'payout_all_time_display',
        'site_revenue_all_time_display',
        'status_badge',
    )
    list_filter = ('is_active', 'bonus_type', 'starts_at', 'expires_at')
    search_fields = ('code', 'blogger_name')
    autocomplete_fields = ('case',)
    ordering = ('-created_at',)
    readonly_fields = ('blogger_analytics_dashboard', 'created_at', 'updated_at')

    fieldsets = (
        ('Основные параметры промокода', {
            'fields': (
                'code',
                'blogger_percentage',
                'blogger_name',
                'bonus_type',
                'bonus_value',
                'case',
                'is_active',
            )
        }),
        ('Лимиты и сроки действия', {
            'fields': (
                'max_uses',
                'used_count',
                'starts_at',
                'expires_at',
                'min_deposit',
                'max_bonus',
            )
        }),
        ('Финансовая статистика и расчет выплат блогеру', {
            'fields': ('blogger_analytics_dashboard',),
            'classes': ('wide',),
        }),
        ('Служебная информация', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def has_view_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_manage_promocodes') or has_admin_perm(request.user, 'can_view_blogger_stats')

    def has_add_permission(self, request):
        return has_admin_perm(request.user, 'can_manage_promocodes')

    def has_change_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_manage_promocodes') or has_admin_perm(request.user, 'can_edit_blogger_percent')

    def has_delete_permission(self, request, obj=None):
        return has_admin_perm(request.user, 'can_manage_promocodes')

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            if not has_admin_perm(request.user, 'can_edit_blogger_percent'):
                ro.extend(['blogger_percentage', 'blogger_name'])
            if not has_admin_perm(request.user, 'can_manage_promocodes'):
                ro.extend(['code', 'bonus_type', 'bonus_value', 'case', 'is_active', 'max_uses', 'starts_at', 'expires_at', 'min_deposit', 'max_bonus'])
        return ro

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        self.current_request = request
        return super().changeform_view(request, object_id, form_url, extra_context=extra_context)

    @admin.display(description="% блогера", ordering='blogger_percentage')
    def blogger_percentage_display(self, obj):
        pct = obj.blogger_percentage or Decimal('0.00')
        if pct > 0:
            name_part = format_html('<br><span style="color: #94a3b8; font-size: 10px; font-weight: normal;">{}</span>', obj.blogger_name) if obj.blogger_name else ''
            return format_html('<strong style="color: #38bdf8; font-size: 13px;">{}%</strong>{}', pct, name_part)
        return format_html('<span style="color: #64748b;">0%</span>')

    @admin.display(description="Пользователей")
    def users_count_display(self, obj):
        count = obj.uses.count()
        return format_html('<strong>{}</strong>', count)

    @admin.display(description="Проигрыш (сегодня)")
    def loss_today_display(self, obj):
        stats = obj.get_stats_today()
        return format_html('<span style="color: #f87171; font-weight: 600;">{} UC</span>', f"{stats['net_loss']:.2f}")

    @admin.display(description="Выплата блогеру (сегодня)")
    def payout_today_display(self, obj):
        stats = obj.get_stats_today()
        return format_html('<span style="color: #eab308; font-weight: 700;">{} UC</span>', f"{stats['blogger_payout']:.2f}")

    @admin.display(description="Доход сайта (сегодня)")
    def site_revenue_today_display(self, obj):
        stats = obj.get_stats_today()
        return format_html('<span style="color: #22c55e; font-weight: 700;">{} UC</span>', f"{stats['site_revenue']:.2f}")

    @admin.display(description="Проигрыш (всё время)")
    def loss_all_time_display(self, obj):
        stats = obj.get_stats_all_time()
        return format_html('<span style="color: #f87171; font-weight: 600;">{} UC</span>', f"{stats['net_loss']:.2f}")

    @admin.display(description="Выплата блогеру (всё время)")
    def payout_all_time_display(self, obj):
        stats = obj.get_stats_all_time()
        return format_html('<strong style="color: #ffd700; font-size: 13px;">{} UC</strong>', f"{stats['blogger_payout']:.2f}")

    @admin.display(description="Доход сайта (всё время)")
    def site_revenue_all_time_display(self, obj):
        stats = obj.get_stats_all_time()
        return format_html('<strong style="color: #4ade80; font-size: 13px;">{} UC</strong>', f"{stats['site_revenue']:.2f}")

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

    @admin.display(description="Панель аналитики блогера")
    def blogger_analytics_dashboard(self, obj):
        if not obj.pk:
            return format_html('<p style="color: #64748b;">Сохраните промокод для отображения аналитики.</p>')

        request = getattr(self, 'current_request', None)
        period = request.GET.get('period', 'all') if request else 'all'
        date_from_str = request.GET.get('date_from', '').strip() if request else ''
        date_to_str = request.GET.get('date_to', '').strip() if request else ''

        from datetime import datetime, time, timedelta
        from django.utils import timezone

        now = timezone.now()
        date_from = None
        date_to = None
        period_title = "За всё время"

        if period == 'today':
            date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
            date_to = now
            period_title = "Сегодня"
        elif period == 'yesterday':
            start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            date_from = start_today - timedelta(days=1)
            date_to = start_today
            period_title = "Вчера"
        elif period == '7d':
            date_from = now - timedelta(days=7)
            date_to = now
            period_title = "Последние 7 дней"
        elif period == '30d':
            date_from = now - timedelta(days=30)
            date_to = now
            period_title = "Последние 30 дней"
        elif period == 'custom' and date_from_str:
            try:
                df = datetime.strptime(date_from_str, '%Y-%m-%d')
                date_from = timezone.make_aware(datetime.combine(df, time.min))
                if date_to_str:
                    dt = datetime.strptime(date_to_str, '%Y-%m-%d')
                    date_to = timezone.make_aware(datetime.combine(dt, time.max))
                else:
                    date_to = now
                period_title = f"Период: {date_from_str} — {date_to_str or 'сейчас'}"
            except Exception:
                date_from = None
                date_to = None
                period_title = "За всё время"

        # Stats for active filter
        stats = obj.get_stats_for_period(date_from=date_from, date_to=date_to)
        
        # Today & All Time fast metrics
        today_stats = obj.get_stats_today()
        all_time_stats = obj.get_stats_all_time()

        # Daily breakdown and users breakdown
        daily_rows = obj.get_daily_breakdown(date_from=date_from, date_to=date_to)
        user_rows = obj.get_referred_users_breakdown(date_from=date_from, date_to=date_to)

        # Build Daily rows HTML
        daily_table_html = ""
        if daily_rows:
            for r in daily_rows:
                daily_table_html += f"""
                <tr style="border-bottom: 1px solid #1e293b;">
                    <td style="padding: 10px 14px; font-weight: 700; color: #f1f5f9;">{r['date_str']}</td>
                    <td style="padding: 10px 14px; text-align: center; color: #cbd5e1;">{r['openings_count']}</td>
                    <td style="padding: 10px 14px; text-align: right; color: #94a3b8;">{r['spent']:.2f} UC</td>
                    <td style="padding: 10px 14px; text-align: right; color: #38bdf8;">{r['won']:.2f} UC</td>
                    <td style="padding: 10px 14px; text-align: right; font-weight: 700; color: #f87171;">{r['net_loss']:.2f} UC</td>
                    <td style="padding: 10px 14px; text-align: center; font-weight: 700; color: #38bdf8;">{r['blogger_percentage']}%</td>
                    <td style="padding: 10px 14px; text-align: right; font-weight: 800; color: #ffd700; background: rgba(234, 179, 8, 0.07);">{r['blogger_payout']:.2f} UC</td>
                    <td style="padding: 10px 14px; text-align: right; font-weight: 800; color: #4ade80; background: rgba(34, 197, 94, 0.07);">{r['site_revenue']:.2f} UC</td>
                </tr>
                """
        else:
            daily_table_html = """
            <tr>
                <td colspan="8" style="padding: 25px; text-align: center; color: #64748b;">
                    Нет данных об открытиях кейсов за выбранный период.
                </td>
            </tr>
            """

        # Build Users rows HTML
        users_table_html = ""
        if user_rows:
            for u in user_rows:
                users_table_html += f"""
                <tr style="border-bottom: 1px solid #1e293b;">
                    <td style="padding: 9px 12px; font-weight: 700; color: #f8fafc;">{u['username']}</td>
                    <td style="padding: 9px 12px; color: #64748b; font-size: 12px;">{u['used_at_str']}</td>
                    <td style="padding: 9px 12px; text-align: center; color: #cbd5e1;">{u['openings_count']}</td>
                    <td style="padding: 9px 12px; text-align: right; color: #94a3b8;">{u['spent']:.2f} UC</td>
                    <td style="padding: 9px 12px; text-align: right; color: #38bdf8;">{u['won']:.2f} UC</td>
                    <td style="padding: 9px 12px; text-align: right; font-weight: 700; color: #f87171;">{u['net_loss']:.2f} UC</td>
                    <td style="padding: 9px 12px; text-align: right; font-weight: 800; color: #ffd700;">{u['blogger_payout']:.2f} UC</td>
                </tr>
                """
        else:
            users_table_html = """
            <tr>
                <td colspan="7" style="padding: 20px; text-align: center; color: #64748b;">
                    Промокод еще не был активирован пользователями.
                </td>
            </tr>
            """

        def chip_style(is_curr):
            if is_curr:
                return "background: #a855f7; color: #fff; font-weight: 700; border: 1px solid #c084fc; padding: 6px 14px; border-radius: 20px; text-decoration: none; font-size: 12px; display: inline-block;"
            return "background: #1e293b; color: #94a3b8; font-weight: 600; border: 1px solid #334155; padding: 6px 14px; border-radius: 20px; text-decoration: none; font-size: 12px; display: inline-block;"

        return format_html(f"""
        <div style="background: #0b0f19; border: 1px solid #334155; border-radius: 12px; padding: 22px; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin-top: 10px;">
            
            <!-- Header with Blogger Info -->
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 16px; margin-bottom: 20px; flex-wrap: wrap; gap: 12px;">
                <div>
                    <h3 style="margin: 0; font-size: 18px; color: #fff; font-weight: 800; letter-spacing: 0.5px;">
                        📊 Финансовая статистика промокода: <span style="color: #ec4899;">{obj.code}</span>
                    </h3>
                    <div style="color: #94a3b8; font-size: 13px; margin-top: 4px;">
                        Блогер: <strong style="color: #f1f5f9;">{obj.blogger_name or 'Не указан'}</strong> &bull; 
                        Процент от чистого проигрыша: <strong style="color: #38bdf8; font-size: 14px;">{obj.blogger_percentage}%</strong>
                    </div>
                </div>

                <div style="background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 6px 14px; text-align: right;">
                    <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Текущий фильтр</div>
                    <div style="font-size: 13px; font-weight: 800; color: #38bdf8;">{period_title}</div>
                </div>
            </div>

            <!-- Date Filter Bar -->
            <div style="background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px 18px; margin-bottom: 22px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px;">
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <span style="font-size: 12px; font-weight: 700; color: #94a3b8; margin-right: 6px; text-transform: uppercase;">Период:</span>
                    <a href="?period=today" style="{chip_style(period == 'today')}">Сегодня</a>
                    <a href="?period=yesterday" style="{chip_style(period == 'yesterday')}">Вчера</a>
                    <a href="?period=7d" style="{chip_style(period == '7d')}">7 дней</a>
                    <a href="?period=30d" style="{chip_style(period == '30d')}">30 дней</a>
                    <a href="?period=all" style="{chip_style(period == 'all')}">Всё время</a>
                </div>

                <form method="get" action="" style="display: flex; align-items: center; gap: 8px; margin: 0;">
                    <input type="hidden" name="period" value="custom" />
                    <input type="date" name="date_from" value="{date_from_str}" style="background: #0f172a; border: 1px solid #334155; color: #fff; padding: 5px 10px; border-radius: 6px; font-size: 12px;" title="Дата начала" />
                    <span style="color: #64748b;">—</span>
                    <input type="date" name="date_to" value="{date_to_str}" style="background: #0f172a; border: 1px solid #334155; color: #fff; padding: 5px 10px; border-radius: 6px; font-size: 12px;" title="Дата окончания" />
                    <button type="submit" style="background: #3b82f6; color: #fff; border: none; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer;">Показать</button>
                </form>
            </div>

            <!-- KPI Metric Cards Grid for Filtered Period -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 25px;">
                
                <div style="background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; text-align: center;">
                    <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 700; margin-bottom: 6px;">👥 Привлечено юзеров</div>
                    <div style="font-size: 24px; font-weight: 900; color: #f8fafc;">{stats['users_count']}</div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 4px;">активаций промокода</div>
                </div>

                <div style="background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; text-align: center;">
                    <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 700; margin-bottom: 6px;">🎰 Потрачено на кейсы</div>
                    <div style="font-size: 22px; font-weight: 900; color: #cbd5e1;">{stats['total_spent']:.2f} <span style="font-size: 14px;">UC</span></div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 4px;">открытий: {stats['openings_count']}</div>
                </div>

                <div style="background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; text-align: center;">
                    <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 700; margin-bottom: 6px;">🎁 Выиграно скинов</div>
                    <div style="font-size: 22px; font-weight: 900; color: #38bdf8;">{stats['total_won']:.2f} <span style="font-size: 14px;">UC</span></div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 4px;">стоимость дропа</div>
                </div>

                <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 10px; padding: 14px; text-align: center;">
                    <div style="font-size: 11px; color: #fca5a5; text-transform: uppercase; font-weight: 700; margin-bottom: 6px;">📉 Чистый проигрыш</div>
                    <div style="font-size: 24px; font-weight: 900; color: #ef4444;">{stats['net_loss']:.2f} <span style="font-size: 14px;">UC</span></div>
                    <div style="font-size: 11px; color: #f87171; margin-top: 4px;">База для расчёта %</div>
                </div>

                <div style="background: rgba(234, 179, 8, 0.08); border: 1px solid rgba(234, 179, 8, 0.3); border-radius: 10px; padding: 14px; text-align: center;">
                    <div style="font-size: 11px; color: #fde047; text-transform: uppercase; font-weight: 700; margin-bottom: 6px;">💰 К выплате блогеру ({stats['blogger_percentage']}%)</div>
                    <div style="font-size: 24px; font-weight: 900; color: #ffd700;">{stats['blogger_payout']:.2f} <span style="font-size: 14px;">UC</span></div>
                    <div style="font-size: 11px; color: #facc15; margin-top: 4px;">Вознаграждение</div>
                </div>

                <div style="background: rgba(34, 197, 94, 0.08); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 10px; padding: 14px; text-align: center;">
                    <div style="font-size: 11px; color: #86efac; text-transform: uppercase; font-weight: 700; margin-bottom: 6px;">🏢 Доход сайта</div>
                    <div style="font-size: 24px; font-weight: 900; color: #22c55e;">{stats['site_revenue']:.2f} <span style="font-size: 14px;">UC</span></div>
                    <div style="font-size: 11px; color: #4ade80; margin-top: 4px;">После выплаты блогеру</div>
                </div>

            </div>

            <!-- Quick Compare: Today vs All Time -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 25px;">
                <div style="background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 700; color: #94a3b8; font-size: 13px;">📅 СЕГОДНЯ:</span>
                    <div style="font-size: 13px;">
                        Проигрыш: <strong style="color: #f87171;">{today_stats['net_loss']:.2f} UC</strong> &bull; 
                        Блогеру: <strong style="color: #ffd700;">{today_stats['blogger_payout']:.2f} UC</strong> &bull; 
                        Сайту: <strong style="color: #4ade80;">{today_stats['site_revenue']:.2f} UC</strong>
                    </div>
                </div>

                <div style="background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 700; color: #94a3b8; font-size: 13px;">🌐 ВСЁ ВРЕМЯ:</span>
                    <div style="font-size: 13px;">
                        Проигрыш: <strong style="color: #f87171;">{all_time_stats['net_loss']:.2f} UC</strong> &bull; 
                        Блогеру: <strong style="color: #ffd700;">{all_time_stats['blogger_payout']:.2f} UC</strong> &bull; 
                        Сайту: <strong style="color: #4ade80;">{all_time_stats['site_revenue']:.2f} UC</strong>
                    </div>
                </div>
            </div>

            <!-- Table 1: Daily Breakdown -->
            <div style="margin-bottom: 25px;">
                <h4 style="margin: 0 0 12px 0; font-size: 15px; color: #f1f5f9; font-weight: 800; display: flex; align-items: center; gap: 8px;">
                    <span>📅 Детализация расчётов по дням</span>
                </h4>
                
                <div style="overflow-x: auto; border: 1px solid #1e293b; border-radius: 8px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                        <thead>
                            <tr style="background: #1e293b; color: #94a3b8; font-size: 11px; text-transform: uppercase;">
                                <th style="padding: 10px 14px;">Дата</th>
                                <th style="padding: 10px 14px; text-align: center;">Открытий</th>
                                <th style="padding: 10px 14px; text-align: right;">Потрачено</th>
                                <th style="padding: 10px 14px; text-align: right;">Выиграно</th>
                                <th style="padding: 10px 14px; text-align: right; color: #f87171;">Проигрыш</th>
                                <th style="padding: 10px 14px; text-align: center; color: #38bdf8;">% блогера</th>
                                <th style="padding: 10px 14px; text-align: right; color: #ffd700;">Выплата блогеру</th>
                                <th style="padding: 10px 14px; text-align: right; color: #4ade80;">Доход сайта</th>
                            </tr>
                        </thead>
                        <tbody>
                            {daily_table_html}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Table 2: Referred Users Breakdown -->
            <div>
                <h4 style="margin: 0 0 12px 0; font-size: 15px; color: #f1f5f9; font-weight: 800; display: flex; align-items: center; gap: 8px;">
                    <span>👥 Привлеченные пользователи ({len(user_rows)})</span>
                </h4>
                
                <div style="overflow-x: auto; border: 1px solid #1e293b; border-radius: 8px;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                        <thead>
                            <tr style="background: #1e293b; color: #94a3b8; font-size: 11px; text-transform: uppercase;">
                                <th style="padding: 9px 12px;">Пользователь</th>
                                <th style="padding: 9px 12px;">Дата активации</th>
                                <th style="padding: 9px 12px; text-align: center;">Открытий</th>
                                <th style="padding: 9px 12px; text-align: right;">Потрачено</th>
                                <th style="padding: 9px 12px; text-align: right;">Выиграно</th>
                                <th style="padding: 9px 12px; text-align: right; color: #f87171;">Проигрыш</th>
                                <th style="padding: 9px 12px; text-align: right; color: #ffd700;">Выплата блогеру</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users_table_html}
                        </tbody>
                    </table>
                </div>
            </div>

        </div>
        """)

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


@admin.register(BloggerPayout)
class BloggerPayoutAdmin(admin.ModelAdmin):
    list_display = ('promo_code', 'blogger_name_display', 'amount_display', 'period', 'admin_user', 'created_at')
    list_filter = ('period', 'created_at', 'promo_code')
    search_fields = ('promo_code__code', 'promo_code__blogger_name', 'period', 'admin_user__username', 'comment')
    autocomplete_fields = ('promo_code',)
    ordering = ('-created_at',)

    def blogger_name_display(self, obj):
        return obj.promo_code.blogger_name or "—"
    blogger_name_display.short_description = "Блогер"

    def amount_display(self, obj):
        return format_html('<strong style="color: #38bdf8; font-size: 14px;">{} UC</strong>', f"{obj.amount:,.2f}".replace(',', ' '))
    amount_display.short_description = "Выплачено"

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser



# =========================================================================
# LIVE CYBER DASHBOARD INJECTION FOR ADMIN INDEX
# =========================================================================
from .admin_dashboard import get_dashboard_context

_original_admin_index = admin.site.index

def custom_admin_index(request, extra_context=None):
    try:
        ctx = get_dashboard_context(request)
    except Exception:
        ctx = {}
    if extra_context:
        ctx.update(extra_context)
    return _original_admin_index(request, extra_context=ctx)

admin.site.index = custom_admin_index

