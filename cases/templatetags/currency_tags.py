from django import template
from django.utils.safestring import mark_safe
from payments.currency import (
    get_currency_rates, uc_to_usd, uc_to_uzs,
    format_uc, format_usd_approx, format_uzs_approx
)

register = template.Library()

@register.filter(name='uc')
@register.filter(name='uc_format')
def uc_filter(value, suffix=True):
    """
    Renders UC value:
      60 -> '60 UC'
      325.50 -> '325.50 UC'
    """
    return format_uc(value, suffix=bool(suffix))

@register.filter(name='uc_amount')
def uc_amount_filter(value):
    """
    Renders UC numerical value without 'UC' text suffix:
      60 -> '60'
    """
    return format_uc(value, suffix=False)

@register.filter(name='usd_approx')
def usd_approx_filter(value):
    """
    Renders approximate USD: '≈ $1.25'
    """
    return format_usd_approx(value)

@register.filter(name='uzs_approx')
def uzs_approx_filter(value):
    """
    Renders approximate UZS: '≈ 15 000 UZS'
    """
    return format_uzs_approx(value)

@register.simple_tag
def uc_icon(size=18, extra_class=''):
    """
    Renders standard UC icon image tag.
    """
    html = f'<img src="/static/images/uc_icon.svg" class="uc-icon {extra_class}" width="{size}" height="{size}" alt="UC" />'
    return mark_safe(html)

@register.simple_tag
def uc_badge(value, show_usd=True, size=18):
    """
    Renders unified UC price badge with icon and optional USD approximation:
    [ICON] 60 UC ≈ $1.25
    """
    uc_text = format_uc(value)
    usd_text = format_usd_approx(value) if show_usd else ""
    
    usd_html = f'<span class="usd-approx">{usd_text}</span>' if show_usd else ""
    html = f'''<span class="uc-price-wrap">
        <span class="uc-badge"><img src="/static/images/uc_icon.svg" class="uc-icon" width="{size}" height="{size}" alt="UC" /><span class="uc-val">{uc_text}</span></span>
        {usd_html}
    </span>'''
    return mark_safe(html)
