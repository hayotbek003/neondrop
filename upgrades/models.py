from django.db import models
from django.contrib.auth.models import User
from cases.models import Item

class UpgradeAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='upgrades', verbose_name="Пользователь")
    source_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='upgrades_from', verbose_name="Исходный скин")
    target_item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='upgrades_to', verbose_name="Целевой скин")
    chance = models.FloatField(verbose_name="Шанс успеха (%)")
    roll = models.FloatField(verbose_name="Выпавшее число (%)")
    is_success = models.BooleanField(verbose_name="Успешен")
    server_seed = models.CharField(max_length=64, blank=True, verbose_name="Server Seed")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время попытки")

    class Meta:
        verbose_name = "Попытка апгрейда"
        verbose_name_plural = "Попытки апгрейда"
        ordering = ['-created_at']

    def __str__(self):
        res = "УСПЕХ" if self.is_success else "НЕУДАЧА"
        return f"{self.user.username}: {self.source_item.name} -> {self.target_item.name} [{self.chance:.2f}%] -> {res}"
