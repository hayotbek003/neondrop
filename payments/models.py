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
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма ($)")
    balance_before = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Баланс до ($)")
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Баланс после ($)")
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
        return f"[{self.get_transaction_type_display()}] {self.user.username}: {sign}${self.amount} ({self.get_status_display()})"
