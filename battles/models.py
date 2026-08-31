from django.db import models
from django.contrib.auth.models import User
from cases.models import Case, Item
from decimal import Decimal

class Battle(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Ожидание игроков'),
        ('in_progress', 'Идет битва'),
        ('finished', 'Завершена'),
    ]

    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_battles', verbose_name="Создатель")
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='battles', verbose_name="Кейс")
    rounds_count = models.PositiveIntegerField(default=1, verbose_name="Количество раундов (кейсов)")
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Стоимость участия ($)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting', verbose_name="Статус")
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='won_battles', verbose_name="Победитель")
    is_bot_opponent = models.BooleanField(default=False, verbose_name="Против бота")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Битва кейсов"
        verbose_name_plural = "Битвы кейсов"
        ordering = ['-created_at']

    def __str__(self):
        return f"Битва #{self.id}: {self.case.name} x{self.rounds_count} (${self.total_cost})"

class BattlePlayer(models.Model):
    battle = models.ForeignKey(Battle, on_delete=models.CASCADE, related_name='players', verbose_name="Битва")
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='battle_participations', verbose_name="Пользователь")
    is_bot = models.BooleanField(default=False, verbose_name="Бот")
    bot_name = models.CharField(max_length=100, default='CyberBot', verbose_name="Имя бота")
    total_loot_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Итоговый выигрыш ($)")

    def __str__(self):
        name = self.bot_name if self.is_bot else (self.user.username if self.user else "Unknown")
        return f"{name} в битве #{self.battle.id}"

class BattleRound(models.Model):
    battle = models.ForeignKey(Battle, on_delete=models.CASCADE, related_name='rounds', verbose_name="Битва")
    round_number = models.PositiveIntegerField(verbose_name="Номер раунда")
    player = models.ForeignKey(BattlePlayer, on_delete=models.CASCADE, related_name='round_drops', verbose_name="Игрок")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, verbose_name="Выпавший скин")

    class Meta:
        ordering = ['round_number', 'id']

    def __str__(self):
        return f"Раунд {self.round_number}: {self.player} -> {self.item.name}"
