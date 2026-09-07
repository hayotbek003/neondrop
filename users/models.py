from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('100.00'), verbose_name="Баланс (UC)")
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
