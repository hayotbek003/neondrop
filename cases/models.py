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
    value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Стоимость ($)")
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

    def __str__(self):
        return f"{self.name} (${self.value})"

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
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена открытия ($)")
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

    def __str__(self):
        return f"{self.name} (${self.price})"

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
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Цена кейса на момент открытия")
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
        return f"{self.user.username} открыл {self.case.name} -> {self.item.name} (${self.item.value})"
