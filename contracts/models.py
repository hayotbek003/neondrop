from django.db import models
from django.contrib.auth.models import User
from cases.models import Item

class Contract(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='contracts', verbose_name="Пользователь")
    total_input_value = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма вложенных предметов (UC)")
    reward_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='contract_rewards', verbose_name="Полученный скин")
    items_count = models.PositiveIntegerField(default=3, verbose_name="Количество вложенных предметов")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата контракта")

    class Meta:
        verbose_name = "Контракт обмена"
        verbose_name_plural = "Контракты обмена"
        ordering = ['-created_at']

    def __str__(self):
        return f"Контракт #{self.id} от {self.user.username}: {self.items_count} предм. ({self.total_input_value} UC) -> {self.reward_item.name} ({self.reward_item.value} UC)"

class ContractInputItem(models.Model):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='input_items', verbose_name="Контракт")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, verbose_name="Предмет")

    def __str__(self):
        return f"{self.contract.id} - {self.item.name}"
