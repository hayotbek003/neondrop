from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from datetime import timedelta
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название категории")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="Слаг")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Категория кейсов"
        verbose_name_plural = "Категории кейсов"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Item(models.Model):
    RARITY_CHOICES = [
        ('knife', '★ Нож / Особое (Золотое)'),
        ('covert', 'Тайное (Красное)'),
        ('classified', 'Засекреченное (Розовое)'),
        ('restricted', 'Запрещенное (Фиолетовое)'),
        ('mil_spec', 'Армейское качество (Синее)'),
        ('industrial', 'Промышленное качество (Голубое)'),
        ('consumer', 'Ширпотреб (Серое)'),
        # PUBG Rarity Tiers
        ('mythic', 'Мифический (Золотой)'),
        ('legendary', 'Легендарный (Красный)'),
        ('epic', 'Эпический (Розовый)'),
        ('rare', 'Редкий (Синий)'),
        ('uncommon', 'Необычный (Зеленый)'),
        ('common', 'Обычный (Серый)'),
    ]

    RARITY_COLORS = {
        'knife': '#FFD700',
        'covert': '#EB4B4B',
        'classified': '#D32CE6',
        'restricted': '#8847FF',
        'mil_spec': '#4B69FF',
        'industrial': '#5E98D9',
        'consumer': '#B0C3D9',
        # PUBG
        'mythic': '#FFD700',
        'legendary': '#EB4B4B',
        'epic': '#D32CE6',
        'rare': '#4B69FF',
        'uncommon': '#5E98D9',
        'common': '#B0C3D9',
    }

    RARITY_NAMES_RU = {
        'knife': '★ НОЖ',
        'covert': 'ТАЙНОЕ',
        'classified': 'ЗАСЕКРЕЧЕННОЕ',
        'restricted': 'ЗАПРЕЩЕННОЕ',
        'mil_spec': 'АРМЕЙСКОЕ КАЧЕСТВО',
        'industrial': 'ПРОМЫШЛЕННОЕ',
        'consumer': 'ШИРПОТРЕБ',
        # PUBG
        'mythic': 'МИФИЧЕСКИЙ',
        'legendary': 'ЛЕГЕНДАРНЫЙ',
        'epic': 'ЭПИЧЕСКИЙ',
        'rare': 'РЕДКИЙ',
        'uncommon': 'НЕОБЫЧНЫЙ',
        'common': 'ОБЫЧНЫЙ',
    }

    game = models.CharField(max_length=50, default="PUBG", db_index=True, verbose_name="Игра")
    weapon_type = models.CharField(max_length=100, verbose_name="Тип оружия", default="AK-47")
    skin_name = models.CharField(max_length=100, verbose_name="Название скина", default="Asiimov")
    name = models.CharField(max_length=200, verbose_name="Полное название", blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Стоимость (UC)")
    rarity = models.CharField(max_length=30, choices=RARITY_CHOICES, default='mil_spec', verbose_name="Редкость")
    rarity_color = models.CharField(max_length=20, default='#4B69FF', verbose_name="Цвет редкости (HEX)")
    quality = models.CharField(max_length=100, blank=True, default="", verbose_name="Качество")
    item_type = models.CharField(max_length=100, blank=True, default="skin", verbose_name="Тип предмета")
    source_id = models.CharField(max_length=150, blank=True, null=True, db_index=True, verbose_name="Source ID")
    source_url = models.CharField(max_length=500, blank=True, null=True, db_index=True, verbose_name="Source URL")
    source_image_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="Source Image URL")
    image = models.ImageField(upload_to='items/', blank=True, null=True, verbose_name="Изображение предмета")
    image_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="URL Изображения / SVG ID")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Предмет / Скин"
        verbose_name_plural = "Предметы / Скины"
        ordering = ['-value']

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"{self.weapon_type} | {self.skin_name}"
        if not self.rarity_color or self.rarity_color == '#4B69FF':
            self.rarity_color = self.RARITY_COLORS.get(self.rarity, '#4B69FF')
        super().save(*args, **kwargs)

    @property
    def rarity_display_ru(self):
        return self.RARITY_NAMES_RU.get(self.rarity, self.get_rarity_display())

    @property
    def display_image(self):
        if self.image_url and (self.image_url.startswith('http://') or self.image_url.startswith('https://') or self.image_url.startswith('/')):
            return self.image_url
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass
        # Static file fallback based on slug or name
        from django.conf import settings
        from pathlib import Path
        from django.utils.text import slugify

        slug = slugify(self.name or f"{self.weapon_type}-{self.skin_name}")
        static_candidate = Path(settings.BASE_DIR) / 'static' / 'items' / f"{slug}.png"
        if static_candidate.is_file():
            return f"{settings.STATIC_URL}items/{slug}.png"
        return None


    def __str__(self):
        return f"{self.name} ({self.value} UC)"

class Case(models.Model):
    THEME_CHOICES = [
        ('neon-green', 'Neon Green (Зеленый)'),
        ('cyber-pink', 'Cyber Pink (Розовый/Маджента)'),
        ('galaxy-purple', 'Galaxy Purple (Фиолетовый)'),
        ('frost-cyan', 'Frost Cyan (Ледяной циан)'),
        ('demon-orange', 'Demon Orange (Огненный)'),
        ('godlike-gold', 'Godlike Gold (Золотой)'),
        ('luxury-silver', 'Luxury Silver (Серебряный)'),
        ('supreme-red', 'Supreme Red (Кровавый)'),
    ]

    THEME_ACCENT_COLORS = {
        'neon-green': '#22c55e',
        'cyber-pink': '#ec4899',
        'galaxy-purple': '#a855f7',
        'frost-cyan': '#06b6d4',
        'demon-orange': '#f97316',
        'godlike-gold': '#eab308',
        'luxury-silver': '#94a3b8',
        'supreme-red': '#ef4444',
    }

    name = models.CharField(max_length=150, verbose_name="Название кейса")
    slug = models.SlugField(max_length=150, unique=True, verbose_name="Слаг")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='cases', verbose_name="Категория")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена открытия (UC)")
    image = models.ImageField(upload_to='cases/', blank=True, null=True, verbose_name="Изображение кейса")
    image_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="URL Изображения / SVG ID")
    color_theme = models.CharField(max_length=30, choices=THEME_CHOICES, default='cyber-pink', verbose_name="Цветовая тема")
    active = models.BooleanField(default=True, verbose_name="Активен")
    is_popular = models.BooleanField(default=False, verbose_name="Популярный кейс (на главной)")
    is_new = models.BooleanField(default=False, verbose_name="Новый кейс")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Кейс"
        verbose_name_plural = "Кейсы"
        ordering = ['order', 'price']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def accent_color(self):
        return self.THEME_ACCENT_COLORS.get(self.color_theme, '#ec4899')

    @property
    def display_image(self):
        if self.image_url and (self.image_url.startswith('http://') or self.image_url.startswith('https://') or self.image_url.startswith('/')):
            return self.image_url
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass
        # Static file fallback based on case slug
        from django.conf import settings
        from pathlib import Path

        if self.slug:
            clean_slug = self.slug.replace('-', '_')
            static_case = Path(settings.BASE_DIR) / 'static' / 'cases' / f"{clean_slug}.jpg"
            if static_case.is_file():
                return f"{settings.STATIC_URL}cases/{clean_slug}.jpg"
            static_case_dash = Path(settings.BASE_DIR) / 'static' / 'cases' / f"{self.slug}.jpg"
            if static_case_dash.is_file():
                return f"{settings.STATIC_URL}cases/{self.slug}.jpg"
        return None


    def __str__(self):
        return f"{self.name} ({self.price} UC)"

class CaseItem(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='case_items', verbose_name="Кейс")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='case_containments', verbose_name="Предмет")
    weight = models.FloatField(default=10.0, verbose_name="Вес шанса выпадения")

    class Meta:
        verbose_name = "Предмет в кейсе"
        verbose_name_plural = "Предметы в кейсе"
        unique_together = ('case', 'item')
        ordering = ['-weight']

    def __str__(self):
        return f"{self.case.name} -> {self.item.name} (Вес: {self.weight})"

class Opening(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='openings', verbose_name="Пользователь")
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='openings', verbose_name="Кейс")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='openings', verbose_name="Выпавший предмет")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена кейса на момент открытия (UC)")
    server_seed_hash = models.CharField(max_length=64, verbose_name="SHA256 Server Seed Hash")
    server_seed = models.CharField(max_length=64, verbose_name="Server Seed (Открытый ключ)")
    client_seed = models.CharField(max_length=64, verbose_name="Client Seed (Ключ клиента)")
    nonce = models.PositiveIntegerField(default=1, verbose_name="Nonce")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время открытия")

    class Meta:
        verbose_name = "История открытия кейса"
        verbose_name_plural = "История открытий кейсов"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} открыл {self.case.name} -> {self.item.name} ({self.item.value} UC)"

class PersonalCaseChance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personal_chances', verbose_name="Пользователь")
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='personal_chances', verbose_name="Кейс")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='personal_chances', verbose_name="Предмет")
    chance = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Персональный шанс (%)", help_text="Шанс в процентах (0.01 - 100.00)")
    starts_at = models.DateTimeField(verbose_name="Дата начала")
    expires_at = models.DateTimeField(verbose_name="Дата окончания")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Персональный шанс (Personal Case Chance)"
        verbose_name_plural = "Персональные шансы (Personal Case Chances)"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} -> {self.case.name} -> {self.item.name}: {self.chance}%"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.chance < Decimal('0.01') or self.chance > Decimal('100.00'):
            raise ValidationError({'chance': "Шанс должен быть в диапазоне от 0.01% до 100.00%."})
        if self.expires_at and self.starts_at and self.expires_at <= self.starts_at:
            raise ValidationError({'expires_at': "Дата окончания должна быть позже даты начала."})

    @property
    def is_valid_now(self):
        from django.utils import timezone
        now = timezone.now()
        return self.is_active and (self.starts_at <= now <= self.expires_at)

    def normal_chance_percent(self):
        """Calculates normal base chance of this item in this case."""
        case_items = self.case.case_items.all()
        total_weight = sum(ci.weight for ci in case_items)
        if total_weight <= 0:
            return 0.0
        matching = self.case.case_items.filter(item=self.item).first()
        if not matching:
            return 0.0
        return round((matching.weight / total_weight) * 100.0, 2)

class PromoCode(models.Model):
    BONUS_TYPE_CHOICES = [
        ('coins', 'UC / Баланс (UC)'),
        ('percentage', 'Процент к депозиту (%)'),
        ('free_case_opens', 'Бесплатные открытия кейса'),
    ]

    code = models.CharField(max_length=50, unique=True, db_index=True, verbose_name="Промокод")
    blogger_name = models.CharField(max_length=150, blank=True, null=True, verbose_name="Имя / Канал блогера", help_text="Например: YouTube @BloggerName или Telegram @channel")
    blogger_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name="Процент блогера (%)", help_text="Процент от чистого проигрыша привлеченных пользователей (например: 10.00 = 10%)")
    bonus_type = models.CharField(max_length=30, choices=BONUS_TYPE_CHOICES, default='coins', verbose_name="Тип бонуса")
    bonus_value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Значение бонуса (UC / % / Кол-во)")
    max_uses = models.PositiveIntegerField(default=100, verbose_name="Максимум использований (всего)")
    used_count = models.PositiveIntegerField(default=0, verbose_name="Количество использований")
    starts_at = models.DateTimeField(verbose_name="Дата начала")
    expires_at = models.DateTimeField(verbose_name="Дата окончания")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    min_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Мин. депозит для активации (UC)")
    max_bonus = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Макс. сумма бонуса (UC)")
    case = models.ForeignKey(Case, on_delete=models.SET_NULL, null=True, blank=True, related_name='promocodes', verbose_name="Кейс для бесплатных открытий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Промокод (Promo Code)"
        verbose_name_plural = "Промокоды (Promo Codes)"
        ordering = ['-created_at']

    def __str__(self):
        blogger_str = f" [{self.blogger_percentage}%]" if self.blogger_percentage > 0 else ""
        return f"{self.code}{blogger_str} ({self.get_bonus_type_display()}: {self.bonus_value})"

    def clean(self):
        from django.core.exceptions import ValidationError
        self.code = self.code.strip().upper()
        if self.bonus_value <= Decimal('0.00'):
            raise ValidationError({'bonus_value': "Значение бонуса должно быть больше 0."})
        if self.blogger_percentage < Decimal('0.00') or self.blogger_percentage > Decimal('100.00'):
            raise ValidationError({'blogger_percentage': "Процент блогера должен быть от 0.00% до 100.00%."})
        if self.bonus_type == 'free_case_opens' and not self.case:
            raise ValidationError({'case': "Для типа 'Бесплатные открытия' необходимо выбрать кейс."})
        if self.expires_at and self.starts_at and self.expires_at <= self.starts_at:
            raise ValidationError({'expires_at': "Дата окончания должна быть позже даты начала."})

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_valid_now(self):
        from django.utils import timezone
        now = timezone.now()
        return self.is_active and (self.used_count < self.max_uses) and (self.starts_at <= now <= self.expires_at)

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    @property
    def is_limit_reached(self):
        return self.used_count >= self.max_uses

    def get_stats_for_period(self, date_from=None, date_to=None):
        """
        Calculates financial and loss statistics for users referred by this promo code.
        Formula:
          Total Spent = Sum of Opening.price by referred users
          Total Won   = Sum of Opening.item.value by referred users
          Net Loss    = max(0.00, Total Spent - Total Won)
          Blogger Payout = round(Net Loss * (blogger_percentage / 100), 2)
          Site Revenue   = Net Loss - Blogger Payout
        """
        uses = list(self.uses.all())
        user_ids = [u.user_id for u in uses]

        if not user_ids:
            return {
                'users_count': 0,
                'openings_count': 0,
                'total_deposits': Decimal('0.00'),
                'total_spent': Decimal('0.00'),
                'total_won': Decimal('0.00'),
                'net_loss': Decimal('0.00'),
                'blogger_percentage': self.blogger_percentage or Decimal('0.00'),
                'blogger_payout': Decimal('0.00'),
                'site_revenue': Decimal('0.00'),
            }

        user_use_map = {u.user_id: u.used_at for u in uses}
        openings_qs = Opening.objects.filter(user_id__in=user_ids).select_related('item', 'user')

        if date_from:
            openings_qs = openings_qs.filter(created_at__gte=date_from)
        if date_to:
            openings_qs = openings_qs.filter(created_at__lte=date_to)

        valid_openings = [
            op for op in openings_qs
            if op.created_at >= user_use_map.get(op.user_id, op.created_at)
        ]

        total_spent = sum((op.price for op in valid_openings), Decimal('0.00'))
        total_won = sum((op.item.value for op in valid_openings), Decimal('0.00'))
        net_loss = max(Decimal('0.00'), total_spent - total_won)

        blogger_pct = self.blogger_percentage or Decimal('0.00')
        blogger_payout = (net_loss * (blogger_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
        site_revenue = net_loss - blogger_payout

        # Total deposits made by referred users (strictly tracking, 0% commission from deposits!)
        from payments.models import Transaction
        dep_qs = Transaction.objects.filter(
            user_id__in=user_ids,
            transaction_type='deposit',
            status='completed'
        )
        if date_from:
            dep_qs = dep_qs.filter(created_at__gte=date_from)
        if date_to:
            dep_qs = dep_qs.filter(created_at__lte=date_to)
        
        valid_deposits = [
            d for d in dep_qs
            if (d.promo_code_id == self.id) or (d.created_at >= user_use_map.get(d.user_id, d.created_at) - timedelta(minutes=5))
        ]
        total_deposits = sum((d.amount for d in valid_deposits), Decimal('0.00'))

        return {
            'users_count': len(user_ids),
            'openings_count': len(valid_openings),
            'total_deposits': total_deposits,
            'total_spent': total_spent,
            'total_won': total_won,
            'net_loss': net_loss,
            'blogger_percentage': blogger_pct,
            'blogger_payout': blogger_payout,
            'site_revenue': site_revenue,
        }

    def get_stats_today(self):
        from django.utils import timezone
        now = timezone.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_stats_for_period(date_from=start_of_day, date_to=now)

    def get_stats_yesterday(self):
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_yesterday = start_of_today - timedelta(days=1)
        return self.get_stats_for_period(date_from=start_of_yesterday, date_to=start_of_today)

    def get_stats_7_days(self):
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        start_7_days = now - timedelta(days=7)
        return self.get_stats_for_period(date_from=start_7_days, date_to=now)

    def get_stats_30_days(self):
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        start_30_days = now - timedelta(days=30)
        return self.get_stats_for_period(date_from=start_30_days, date_to=now)

    def get_stats_this_month(self):
        from django.utils import timezone
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self.get_stats_for_period(date_from=start_of_month, date_to=now)

    def get_stats_prev_month(self):
        from django.utils import timezone
        from datetime import timedelta
        now = timezone.now()
        start_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_of_prev_month = start_of_this_month - timedelta(microseconds=1)
        start_of_prev_month = end_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self.get_stats_for_period(date_from=start_of_prev_month, date_to=end_of_prev_month)

    def get_stats_all_time(self):
        return self.get_stats_for_period()

    def get_monthly_breakdown(self):
        """
        Groups all activity of referred users by calendar month (e.g. '2026-09', '2026-08').
        Returns list of monthly summary dictionaries with:
          month_key ('YYYY-MM'), month_name, total_deposits, spent, won, net_loss,
          blogger_percentage, blogger_payout, paid_amount, remaining_balance
        """
        from collections import defaultdict
        import calendar
        uses = list(self.uses.all())
        user_ids = [u.user_id for u in uses]
        if not user_ids:
            return []

        user_use_map = {u.user_id: u.used_at for u in uses}
        openings_qs = Opening.objects.filter(user_id__in=user_ids).select_related('item')

        monthly_map = defaultdict(lambda: {
            'openings_count': 0,
            'spent': Decimal('0.00'),
            'won': Decimal('0.00'),
            'deposits': Decimal('0.00')
        })

        for op in openings_qs:
            if op.created_at >= user_use_map.get(op.user_id, op.created_at):
                m_key = op.created_at.strftime('%Y-%m')
                monthly_map[m_key]['openings_count'] += 1
                monthly_map[m_key]['spent'] += op.price
                monthly_map[m_key]['won'] += op.item.value

        from payments.models import Transaction
        dep_qs = Transaction.objects.filter(
            user_id__in=user_ids,
            transaction_type='deposit',
            status='completed'
        )
        for dep in dep_qs:
            if dep.created_at >= user_use_map.get(dep.user_id, dep.created_at):
                m_key = dep.created_at.strftime('%Y-%m')
                monthly_map[m_key]['deposits'] += dep.amount

        # Also include any months that have recorded payouts even if no openings
        payouts_by_month = defaultdict(Decimal)
        for p in self.payouts.all():
            payouts_by_month[p.period] += p.amount
            if p.period not in monthly_map and len(p.period) == 7 and p.period[4] == '-':
                monthly_map[p.period]

        blogger_pct = self.blogger_percentage or Decimal('0.00')
        months_list = sorted(monthly_map.keys(), reverse=True)
        results = []

        for m_key in months_list:
            data = monthly_map[m_key]
            spent = data['spent']
            won = data['won']
            net_loss = max(Decimal('0.00'), spent - won)
            blogger_payout = (net_loss * (blogger_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
            paid_amount = payouts_by_month.get(m_key, Decimal('0.00'))
            remaining = max(Decimal('0.00'), blogger_payout - paid_amount)

            try:
                y, m = map(int, m_key.split('-'))
                month_names_ru = [
                    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
                ]
                m_label = f"{month_names_ru[m]} {y}"
            except Exception:
                m_label = m_key

            results.append({
                'month_key': m_key,
                'month_label': m_label,
                'openings_count': data['openings_count'],
                'deposits': data['deposits'],
                'spent': spent,
                'won': won,
                'net_loss': net_loss,
                'blogger_percentage': blogger_pct,
                'blogger_payout': blogger_payout,
                'paid_amount': paid_amount,
                'remaining_balance': remaining,
            })

        return results

    def get_daily_breakdown(self, date_from=None, date_to=None):
        from collections import defaultdict
        uses = list(self.uses.all())
        user_ids = [u.user_id for u in uses]
        if not user_ids:
            return []

        user_use_map = {u.user_id: u.used_at for u in uses}
        openings_qs = Opening.objects.filter(user_id__in=user_ids).select_related('item', 'user')

        if date_from:
            openings_qs = openings_qs.filter(created_at__gte=date_from)
        if date_to:
            openings_qs = openings_qs.filter(created_at__lte=date_to)

        daily_map = defaultdict(lambda: {'openings_count': 0, 'spent': Decimal('0.00'), 'won': Decimal('0.00')})

        for op in openings_qs:
            if op.created_at >= user_use_map.get(op.user_id, op.created_at):
                day = op.created_at.date()
                daily_map[day]['openings_count'] += 1
                daily_map[day]['spent'] += op.price
                daily_map[day]['won'] += op.item.value

        rows = []
        blogger_pct = self.blogger_percentage or Decimal('0.00')

        for day in sorted(daily_map.keys(), reverse=True):
            data = daily_map[day]
            spent = data['spent']
            won = data['won']
            net_loss = max(Decimal('0.00'), spent - won)
            blogger_payout = (net_loss * (blogger_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
            site_revenue = net_loss - blogger_payout

            rows.append({
                'date': day,
                'date_str': day.strftime('%d.%m.%Y'),
                'openings_count': data['openings_count'],
                'spent': spent,
                'won': won,
                'net_loss': net_loss,
                'blogger_percentage': blogger_pct,
                'blogger_payout': blogger_payout,
                'site_revenue': site_revenue,
            })

        return rows

    def get_referred_users_breakdown(self, date_from=None, date_to=None):
        uses = list(self.uses.select_related('user').all())
        if not uses:
            return []

        blogger_pct = self.blogger_percentage or Decimal('0.00')
        rows = []

        for use in uses:
            openings_qs = Opening.objects.filter(user=use.user, created_at__gte=use.used_at).select_related('item')
            if date_from:
                openings_qs = openings_qs.filter(created_at__gte=date_from)
            if date_to:
                openings_qs = openings_qs.filter(created_at__lte=date_to)

            openings_list = list(openings_qs)
            spent = sum((op.price for op in openings_list), Decimal('0.00'))
            won = sum((op.item.value for op in openings_list), Decimal('0.00'))
            net_loss = max(Decimal('0.00'), spent - won)
            blogger_payout = (net_loss * (blogger_pct / Decimal('100.00'))).quantize(Decimal('0.01'))
            site_revenue = net_loss - blogger_payout

            rows.append({
                'user': use.user,
                'username': use.user.username,
                'used_at': use.used_at,
                'used_at_str': use.used_at.strftime('%d.%m.%Y %H:%M'),
                'openings_count': len(openings_list),
                'spent': spent,
                'won': won,
                'net_loss': net_loss,
                'blogger_payout': blogger_payout,
                'site_revenue': site_revenue,
            })

        rows.sort(key=lambda x: x['net_loss'], reverse=True)
        return rows

class PromoCodeUse(models.Model):
    promo_code = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name='uses', verbose_name="Промокод")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='promocode_uses', verbose_name="Пользователь")
    used_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата использования")
    bonus_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Начисленный бонус (UC)")
    related_transaction = models.ForeignKey('payments.Transaction', on_delete=models.SET_NULL, null=True, blank=True, related_name='promocode_uses', verbose_name="Связанная транзакция")

    class Meta:
        verbose_name = "Использование промокода"
        verbose_name_plural = "Использования промокодов"
        unique_together = ('user', 'promo_code')
        ordering = ['-used_at']

    def __str__(self):
        return f"{self.user.username} использовал {self.promo_code.code} ({self.used_at.strftime('%d.%m.%Y %H:%M')})"

class UserFreeOpening(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='free_openings', verbose_name="Пользователь")
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='user_free_openings', verbose_name="Кейс")
    openings_left = models.PositiveIntegerField(default=0, verbose_name="Осталось бесплатных открытий")
    total_granted = models.PositiveIntegerField(default=0, verbose_name="Всего начислено")
    promo_code = models.ForeignKey(PromoCode, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Промокод")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Бесплатные открытия пользователя"
        verbose_name_plural = "Бесплатные открытия пользователей"
        unique_together = ('user', 'case')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} -> {self.case.name}: {self.openings_left} бесплатных открытий"


class BloggerPayout(models.Model):
    promo_code = models.ForeignKey(PromoCode, on_delete=models.CASCADE, related_name='payouts', verbose_name="Промокод / Блогер")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма выплаты (UC)")
    period = models.CharField(max_length=30, verbose_name="Период выплаты", help_text="Например: 2026-09 или all_time")
    admin_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='blogger_payouts_made', verbose_name="Администратор")
    comment = models.TextField(blank=True, verbose_name="Комментарий / Реквизиты")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата выплаты")

    class Meta:
        verbose_name = "Выплата блогеру"
        verbose_name_plural = "Выплаты блогерам"
        ordering = ['-created_at']

    def __str__(self):
        return f"Выплата {self.amount} UC блогеру {self.promo_code.blogger_name or self.promo_code.code} за {self.period}"


class RngSimulationRun(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='rng_simulations', verbose_name="Кейс")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Запустил")
    num_simulations = models.PositiveIntegerField(verbose_name="Количество симуляций")
    case_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Цена кейса (UC)")
    target_rtp = models.FloatField(verbose_name="Target RTP (%)")
    actual_rtp = models.FloatField(verbose_name="Actual RTP (%)")
    deviation = models.FloatField(verbose_name="Отклонение (%)")
    total_spent = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Потрачено (UC)")
    total_payout = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Выплачено (UC)")
    house_edge = models.FloatField(verbose_name="House Edge (%)")
    chi_square_stat = models.FloatField(verbose_name="Chi-Square статистика")
    p_value = models.FloatField(verbose_name="p-value")
    status = models.CharField(max_length=100, verbose_name="Статус проверки")
    status_level = models.CharField(max_length=20, default='green', verbose_name="Уровень статуса (green/yellow/red)")
    ci_lower = models.FloatField(default=0.0, verbose_name="Доверительный интервал (нижний, %)")
    ci_upper = models.FloatField(default=0.0, verbose_name="Доверительный интервал (верхний, %)")
    server_seed = models.CharField(max_length=64, blank=True, verbose_name="Server Seed")
    client_seed = models.CharField(max_length=64, blank=True, verbose_name="Client Seed")
    item_stats = models.JSONField(default=list, verbose_name="Статистика по предметам")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата запуска")

    class Meta:
        verbose_name = "Результат RNG симуляции"
        verbose_name_plural = "Результаты RNG симуляций"
        ordering = ['-created_at']

    def __str__(self):
        return f"Симуляция {self.case.name}: {self.num_simulations:,} прокруток -> RTP {self.actual_rtp:.2f}% ({self.created_at.strftime('%d.%m.%Y %H:%M')})"


class PubgImportSession(models.Model):
    STATUS_CHOICES = [
        ('preview', 'Ожидает подтверждения (Preview)'),
        ('importing', 'Выполняется импорт'),
        ('completed', 'Импорт успешно завершён'),
        ('failed', 'Ошибка при импорте'),
        ('cancelled', 'Отменён пользователем'),
    ]

    session_id = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="ID сессии импорта")
    filename = models.CharField(max_length=255, verbose_name="Имя файла архива")
    zip_path = models.CharField(max_length=500, verbose_name="Путь к сохранённому архиву")
    filesize_bytes = models.BigIntegerField(default=0, verbose_name="Размер архива (байт)")
    total_items = models.IntegerField(default=0, verbose_name="Всего предметов в архиве")
    new_items_count = models.IntegerField(default=0, verbose_name="Количество новых (NEW)")
    existing_items_count = models.IntegerField(default=0, verbose_name="Количество существующих (EXISTING)")
    error_items_count = models.IntegerField(default=0, verbose_name="Количество ошибок валидации")
    total_images = models.IntegerField(default=0, verbose_name="Количество изображений")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preview', db_index=True, verbose_name="Статус")
    mode = models.CharField(max_length=30, default='add_only', verbose_name="Режим импорта")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Администратор")
    summary_data = models.JSONField(default=dict, blank=True, verbose_name="Итоговая статистика")
    error_message = models.TextField(blank=True, null=True, verbose_name="Сообщение об ошибке")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Сессия импорта PUBG"
        verbose_name_plural = "Сессии импорта PUBG"
        ordering = ['-created_at']

    def __str__(self):
        return f"Импорт PUBG {self.session_id[:8]} ({self.filename}) — {self.get_status_display()}"

    def clean_storage(self):
        """Safely removes temporary zip file if it exists."""
        try:
            from pathlib import Path
            p = Path(self.zip_path)
            if p.exists():
                p.unlink(missing_ok=True)
        except Exception:
            pass

