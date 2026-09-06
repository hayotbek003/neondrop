from decimal import Decimal, ROUND_HALF_UP
from django.core.cache import cache

def get_currency_rates():
    """
    Returns cached currency conversion rates.
    Defaults:
      1 UC = 250 UZS
      1 USD = 12,000 UZS
      -> 1 UC = (250 / 12000) USD ≈ $0.020833 USD
      -> 60 UC = $1.25 USD
    """
    try:
        from payments.models import CurrencySetting
        return CurrencySetting.get_rates()
    except Exception:
        # Fallback if DB not ready
        uc_to_uzs = Decimal('250.00')
        usd_to_uzs = Decimal('12000.00')
        return {
            'uc_to_uzs': uc_to_uzs,
            'usd_to_uzs': usd_to_uzs,
            'uc_to_usd_rate': uc_to_uzs / usd_to_uzs,
        }

def uc_to_usd(uc_amount):
    """
    Converts UC amount to approximate USD value.
    """
    if uc_amount is None:
        return Decimal('0.00')
    if not isinstance(uc_amount, Decimal):
        uc_amount = Decimal(str(uc_amount))
    rates = get_currency_rates()
    usd_val = uc_amount * rates['uc_to_usd_rate']
    return usd_val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def uc_to_uzs(uc_amount):
    """
    Converts UC amount to approximate UZS (сум) value.
    """
    if uc_amount is None:
        return Decimal('0')
    if not isinstance(uc_amount, Decimal):
        uc_amount = Decimal(str(uc_amount))
    rates = get_currency_rates()
    uzs_val = uc_amount * rates['uc_to_uzs']
    return uzs_val.quantize(Decimal('1'), rounding=ROUND_HALF_UP)

def format_uc(uc_amount, suffix=True):
    """
    Formats UC value cleanly:
      60 -> '60 UC'
      325.5 -> '325.50 UC'
    """
    if uc_amount is None:
        return '0 UC' if suffix else '0'
    if not isinstance(uc_amount, Decimal):
        try:
            uc_amount = Decimal(str(uc_amount))
        except Exception:
            return '0 UC' if suffix else '0'
    
    # If whole number, format without decimal places
    if uc_amount % 1 == 0:
        val_str = f"{int(uc_amount):,}".replace(',', ' ')
    else:
        val_str = f"{uc_amount:,.2f}".replace(',', ' ')
    
    return f"{val_str} UC" if suffix else val_str

def format_usd_approx(uc_amount):
    """
    Returns formatted USD string: '≈ $1.25'
    """
    usd_val = uc_to_usd(uc_amount)
    return f"≈ ${usd_val:,.2f}"

def format_uzs_approx(uc_amount):
    """
    Returns formatted UZS string: '≈ 15 000 UZS'
    """
    uzs_val = uc_to_uzs(uc_amount)
    return f"≈ {int(uzs_val):,} UZS".replace(',', ' ')
