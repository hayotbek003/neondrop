from django.db import models
from django.contrib.auth.models import User
from cases.models import Item, Opening

class InventoryItem(models.Model):
    SOURCE_CHOICES = [
        ('case', 'Открытие кейса'),
        ('upgrade', 'Апгрейд'),
        ('contract', 'Контракт'),
        ('battle', 'Битва кейсов'),
        ('admin', 'Начислено администратором'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inventory_items', verbose_name="Пользователь")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='inventory_entries', verbose_name="Предмет")
    is_sold = models.BooleanField(default=False, verbose_name="Продан")
    sold_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Цена продажи ($)")
    sold_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата продажи")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='case', verbose_name="Источник получения")
    opening = models.ForeignKey(Opening, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_drops', verbose_name="Связанное открытие")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата получения")

    class Meta:
        verbose_name = "Предмет в инвентаре"
        verbose_name_plural = "Инвентарь пользователей"
        ordering = ['-created_at']

    def __str__(self):
        status = " (Продан)" if self.is_sold else ""
        return f"{self.user.username} -> {self.item.name} (${self.item.value}){status}"
