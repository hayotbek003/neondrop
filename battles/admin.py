from django.contrib import admin
from .models import Battle, BattlePlayer, BattleRound

class BattlePlayerInline(admin.TabularInline):
    model = BattlePlayer
    extra = 0

class BattleRoundInline(admin.TabularInline):
    model = BattleRound
    extra = 0
    readonly_fields = ('round_number', 'player', 'item')

@admin.register(Battle)
class BattleAdmin(admin.ModelAdmin):
    list_display = ('id', 'creator', 'case', 'rounds_count', 'total_cost', 'status', 'winner', 'created_at')
    list_filter = ('status', 'is_bot_opponent', 'created_at')
    search_fields = ('creator__username', 'winner__username', 'case__name')
    inlines = [BattlePlayerInline, BattleRoundInline]
    ordering = ('-created_at',)
