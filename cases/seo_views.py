import os
from django.http import HttpResponse
from django.conf import settings


def robots_txt_view(request):
    """
    Generates dynamic robots.txt:
    - Allows indexing of all public cases, home, fairness, leaderboard, static, and media
    - Disallows private user profile, inventory, deposit, upgrade, contracts, battles, admin, and APIs
    - References the absolute HTTPS sitemap.xml
    """
    domain = getattr(
        settings,
        'SITE_DOMAIN',
        os.environ.get('SITE_DOMAIN', 'neondrop-ujly.onrender.com')
    ).strip('/')

    lines = [
        "# NEONDROP Robots.txt",
        "User-agent: *",
        "Allow: /",
        "Allow: /cases/",
        "Allow: /fairness/",
        "Allow: /top/",
        "Allow: /users/login/",
        "Allow: /users/register/",
        "Allow: /static/",
        "Allow: /media/",
        "",
        "# Disallow private user accounts, financial transactions, games, and internal APIs",
        "Disallow: /admin/",
        "Disallow: /users/profile/",
        "Disallow: /users/history/",
        "Disallow: /users/settings/",
        "Disallow: /users/google/",
        "Disallow: /inventory/",
        "Disallow: /deposit/",
        "Disallow: /upgrade/",
        "Disallow: /contracts/",
        "Disallow: /battles/",
        "Disallow: /api/",
        "Disallow: /*?*next=*",
        "",
        f"Sitemap: https://{domain}/sitemap.xml",
    ]
    content = "\n".join(lines) + "\n"
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def google_verification_file_view(request, token):
    """
    Handles Google Search Console HTML verification file requests, e.g. /google<token>.html
    """
    expected_token = getattr(
        settings,
        'GOOGLE_SITE_VERIFICATION',
        os.environ.get('GOOGLE_SITE_VERIFICATION', '')
    )
    # Return verification string
    return HttpResponse(f"google-site-verification: google{token}.html", content_type="text/html; charset=utf-8")
