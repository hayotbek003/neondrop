from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('5.00'), verbose_name="Баланс (UC)")
    telegram_username = models.CharField(max_length=100, blank=True, null=True, verbose_name="Telegram Username")
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name="Аватар")
    avatar_url = models.CharField(max_length=300, blank=True, null=True, verbose_name="URL Аватара (fallback)")
    total_opened = models.PositiveIntegerField(default=0, verbose_name="Открыто кейсов")
    total_winnings = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Сумма выигрышей (UC)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата регистрации")

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} (Баланс: {self.balance} UC)"

    @property
    def display_avatar(self):
        if self.avatar:
            return self.avatar.url
        if self.avatar_url:
            return self.avatar_url
        return f"https://api.dicebear.com/7.x/bottts/svg?seed={self.user.username}"


ADMIN_PERMISSIONS_LIST = [
    ('can_view_users', 'Просматривать пользователей', 'Пользователи'),
    ('can_edit_users', 'Редактировать пользователей', 'Пользователи'),
    ('can_view_cases', 'Просматривать кейсы', 'Кейсы'),
    ('can_add_cases', 'Добавлять кейсы', 'Кейсы'),
    ('can_edit_cases', 'Редактировать кейсы', 'Кейсы'),
    ('can_delete_cases', 'Удалять кейсы', 'Кейсы'),
    ('can_add_items', 'Добавлять предметы', 'Предметы'),
    ('can_edit_images', 'Изменять изображения', 'Предметы'),
    ('can_edit_prices', 'Изменять цены', 'Предметы'),
    ('can_edit_case_chances', 'Изменять шансы кейсов', 'Предметы'),
    ('can_manage_promocodes', 'Управлять промокодами', 'Промокоды / Блогеры'),
    ('can_view_blogger_stats', 'Просматривать статистику блогеров', 'Промокоды / Блогеры'),
    ('can_edit_blogger_percent', 'Изменять процент блогеров', 'Промокоды / Блогеры'),
    ('can_view_deposits', 'Просматривать пополнения', 'Финансы'),
    ('can_approve_deposits', 'Подтверждать пополнения', 'Финансы'),
    ('can_view_withdrawals', 'Просматривать выводы', 'Финансы'),
    ('can_approve_withdrawals', 'Одобрять выводы', 'Финансы'),
    ('can_view_backup', 'Просматривать Backup', 'Резервные копии'),
    ('can_create_backup', 'Делать Backup', 'Резервные копии'),
    ('can_restore_backup', 'Восстанавливать Backup', 'Резервные копии'),
]


def has_admin_perm(user, perm_name: str) -> bool:
    """
    Checks if a user has a specific granular admin permission.
    - Superusers always have ALL permissions (True).
    - Inactive or non-staff users have NO permissions (False).
    - Staff users must have the specific permission enabled in AdminPermissionProfile.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    if not user.is_staff:
        return False
    perm_profile = getattr(user, 'admin_permissions', None)
    if not perm_profile:
        return False
    return bool(getattr(perm_profile, perm_name, False))


class AdminPermissionProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_permissions', verbose_name="Администратор")

    # Пользователи
    can_view_users = models.BooleanField(default=False, verbose_name="Просматривать пользователей")
    can_edit_users = models.BooleanField(default=False, verbose_name="Редактировать пользователей")

    # Кейсы
    can_view_cases = models.BooleanField(default=False, verbose_name="Просматривать кейсы")
    can_add_cases = models.BooleanField(default=False, verbose_name="Добавлять кейсы")
    can_edit_cases = models.BooleanField(default=False, verbose_name="Редактировать кейсы")
    can_delete_cases = models.BooleanField(default=False, verbose_name="Удалять кейсы")

    # Предметы, изображения, цены, шансы
    can_add_items = models.BooleanField(default=False, verbose_name="Добавлять предметы")
    can_edit_images = models.BooleanField(default=False, verbose_name="Изменять изображения")
    can_edit_prices = models.BooleanField(default=False, verbose_name="Изменять цены")
    can_edit_case_chances = models.BooleanField(default=False, verbose_name="Изменять шансы кейсов")

    # Промокоды и блогеры
    can_manage_promocodes = models.BooleanField(default=False, verbose_name="Управлять промокодами")
    can_view_blogger_stats = models.BooleanField(default=False, verbose_name="Просматривать статистику блогеров")
    can_edit_blogger_percent = models.BooleanField(default=False, verbose_name="Изменять процент блогеров")

    # Финансы
    can_view_deposits = models.BooleanField(default=False, verbose_name="Просматривать пополнения")
    can_approve_deposits = models.BooleanField(default=False, verbose_name="Подтверждать пополнения")
    can_view_withdrawals = models.BooleanField(default=False, verbose_name="Просматривать выводы")
    can_approve_withdrawals = models.BooleanField(default=False, verbose_name="Одобрять выводы")

    # Резервные копии
    can_view_backup = models.BooleanField(default=False, verbose_name="Просматривать Backup")
    can_create_backup = models.BooleanField(default=False, verbose_name="Делать Backup")
    can_restore_backup = models.BooleanField(default=False, verbose_name="Восстанавливать Backup")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата назначения")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Права администратора"
        verbose_name_plural = "Права администраторов"
        ordering = ['user__username']

    def __str__(self):
        return f"Права администратора: {self.user.username}"

    def active_permissions_count(self):
        return sum(1 for perm, _, _ in ADMIN_PERMISSIONS_LIST if getattr(self, perm, False))


class GoogleAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='google_account', verbose_name="Пользователь")
    google_id = models.CharField(max_length=255, unique=True, db_index=True, verbose_name="Google Sub ID")
    email = models.EmailField(verbose_name="Google Email")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата привязки")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Google аккаунт"
        verbose_name_plural = "Google аккаунты"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} (Google ID: {self.google_id})"
