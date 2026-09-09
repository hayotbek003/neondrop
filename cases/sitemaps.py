import os
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.conf import settings
from cases.models import Case


class CustomSite:
    def __init__(self, domain):
        self.domain = domain
        self.name = 'NEONDROP'


class BaseNeondropSitemap(Sitemap):
    protocol = 'https'

    def get_urls(self, page=1, site=None, protocol=None):
        domain = getattr(
            settings,
            'SITE_DOMAIN',
            os.environ.get('SITE_DOMAIN', 'neondrop-ujly.onrender.com')
        ).strip('/')
        return super().get_urls(page=page, site=CustomSite(domain), protocol='https')


class StaticViewSitemap(BaseNeondropSitemap):
    """
    Sitemap for main public landing pages.
    """
    def items(self):
        return [
            ('cases:home', 1.0, 'daily'),
            ('cases:cases_list', 0.9, 'daily'),
            ('cases:fairness', 0.8, 'weekly'),
            ('cases:top', 0.7, 'daily'),
            ('users:login', 0.5, 'monthly'),
            ('users:register', 0.6, 'monthly'),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class CaseSitemap(BaseNeondropSitemap):
    """
    Dynamic sitemap for all active cases.
    Automatically includes any newly added case without manual edits.
    """
    changefreq = 'daily'
    priority = 0.9

    def items(self):
        return Case.objects.filter(active=True).order_by('-price')

    def location(self, obj):
        return reverse('cases:case_detail', kwargs={'slug': obj.slug})

    def lastmod(self, obj):
        return getattr(obj, 'created_at', None)
