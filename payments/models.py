from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class Transaction(models.Model):
    TYPE_CHOICES = [
        ('deposit', 'Пополнение баланса'),
        ('case_open', 'Открытие кейса'),
        ('item_sell', 'Продажа скина'),
        ('sell_all', 'Массовая продажа скинов'),
        ('upgrade_loss', 'Апгрейд (сгорание скина)'),
        ('upgrade_win', 'Апгрейд (получение скина)'),
        ('contract_craft', 'Крафт по контракту'),
        ('battle_entry', 'Вход в битву кейсов'),
        ('battle_win', 'Выигрыш в битве кейсов'),
        ('promo_bonus', 'Бонус по промокоду'),
        ('admin_adjustment', 'Корректировка администратором'),
    ]

    STATUS_CHOICES = [
        ('completed', 'Успешно завершен'),
        ('pending', 'Ожидает подтверждения'),
        ('rejected', 'Отклонен'),
        ('failed', 'Ошибка транзакции'),
    ]

    PAYMENT_METHODS = [
        ('system', 'Внутриигровой баланс'),
        ('telegram', 'Telegram перевод'),
        ('crypto', 'Криптовалюта'),
        ('card', 'Банковская карта'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions', verbose_name="Пользователь")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма (UC)")
    balance_before = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Баланс до (UC)")
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Баланс после (UC)")
    transaction_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='deposit', verbose_name="Тип операции")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHODS, default='telegram', verbose_name="Метод оплаты")
    telegram_username = models.CharField(max_length=100, blank=True, null=True, verbose_name="Telegram аккаунт")
    reference_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID связанного объекта")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Описание операции")
    idempotency_key = models.CharField(max_length=64, blank=True, null=True, db_index=True, verbose_name="Ключ идемпотентности")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP-адрес инициатора")
    comment = models.TextField(blank=True, null=True, verbose_name="Комментарий администратора")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Транзакция / Запись книги учета"
        verbose_name_plural = "Журнал транзакций (Ledger)"
        ordering = ['-created_at']

    def __str__(self):
        sign = "+" if self.amount > 0 else ""
        return f"[{self.get_transaction_type_display()}] {self.user.username}: {sign}{self.amount} UC ({self.get_status_display()})"


class CurrencySetting(models.Model):
    uc_to_uzs = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('250.00'),
        verbose_name="Курс: 1 UC в UZS (сум)",
        help_text="Например: 250 (тогда 60 UC = 15 000 UZS)"
    )
    usd_to_uzs = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('12000.00'),
        verbose_name="Курс: 1 USD в UZS (сум)",
        help_text="Например: 12000 (тогда 15 000 UZS ≈ $1.25 USD)"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Настройка курсов валют (UC / UZS / USD)"
        verbose_name_plural = "Настройки курсов валют (UC / UZS / USD)"

    def __str__(self):
        return f"1 UC = {self.uc_to_uzs} UZS | 1 USD = {self.usd_to_uzs} UZS (1 UC ≈ ${(self.uc_to_uzs / self.usd_to_uzs):.4f})"

    @classmethod
    def get_rates(cls):
        from django.core.cache import cache
        cached = cache.get('neondrop_currency_rates')
        if cached:
            return cached

        setting = cls.objects.filter(is_active=True).first()
        if not setting:
            setting = cls.objects.create(
                uc_to_uzs=Decimal('250.00'),
                usd_to_uzs=Decimal('12000.00'),
                is_active=True
            )

        uc_to_uzs = setting.uc_to_uzs
        usd_to_uzs = setting.usd_to_uzs if setting.usd_to_uzs > 0 else Decimal('12000.00')
        uc_to_usd_rate = uc_to_uzs / usd_to_uzs

        rates = {
            'uc_to_uzs': uc_to_uzs,
            'usd_to_uzs': usd_to_uzs,
            'uc_to_usd_rate': uc_to_usd_rate,
        }
        cache.set('neondrop_currency_rates', rates, timeout=300)
        return rates

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete('neondrop_currency_rates')

