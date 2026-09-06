from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
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
    ]

    RARITY_COLORS = {
        'knife': '#FFD700',
        'covert': '#EB4B4B',
        'classified': '#D32CE6',
        'restricted': '#8847FF',
        'mil_spec': '#4B69FF',
        'industrial': '#5E98D9',
        'consumer': '#B0C3D9',
    }

    RARITY_NAMES_RU = {
        'knife': '★ НОЖ',
        'covert': 'ТАЙНОЕ',
        'classified': 'ЗАСЕКРЕЧЕННОЕ',
        'restricted': 'ЗАПРЕЩЕННОЕ',
        'mil_spec': 'АРМЕЙСКОЕ КАЧЕСТВО',
        'industrial': 'ПРОМЫШЛЕННОЕ',
        'consumer': 'ШИРПОТРЕБ',
    }

    weapon_type = models.CharField(max_length=100, verbose_name="Тип оружия", default="AK-47")
    skin_name = models.CharField(max_length=100, verbose_name="Название скина", default="Asiimov")
    name = models.CharField(max_length=200, verbose_name="Полное название", blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Стоимость (UC)")
    rarity = models.CharField(max_length=30, choices=RARITY_CHOICES, default='mil_spec', verbose_name="Редкость")
    rarity_color = models.CharField(max_length=20, default='#4B69FF', verbose_name="Цвет редкости (HEX)")
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
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass
        if self.image_url and (self.image_url.startswith('http://') or self.image_url.startswith('https://') or self.image_url.startswith('/')):
            return self.image_url
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
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass
        if self.image_url and (self.image_url.startswith('http://') or self.image_url.startswith('https://') or self.image_url.startswith('/')):
            return self.image_url
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
        return f"{self.code} ({self.get_bonus_type_display()}: {self.bonus_value})"

    def clean(self):
        from django.core.exceptions import ValidationError
        self.code = self.code.strip().upper()
        if self.bonus_value <= Decimal('0.00'):
            raise ValidationError({'bonus_value': "Значение бонуса должно быть больше 0."})
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
