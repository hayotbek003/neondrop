import os
from django.http import HttpResponse, FileResponse
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
        "Allow: /favicon.ico",
        "Allow: /site.webmanifest",
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


def favicon_ico_view(request):
    """
    Serves /favicon.ico directly at the root of the domain for Googlebot,
    search engines, and browsers with status 200 OK.
    """
    for candidate in [
        settings.BASE_DIR / 'static' / 'favicon.ico',
        getattr(settings, 'STATIC_ROOT', settings.BASE_DIR / 'staticfiles') / 'favicon.ico',
        settings.BASE_DIR / 'static' / 'images' / 'favicon.ico',
    ]:
        if candidate.is_file():
            return HttpResponse(candidate.read_bytes(), content_type='image/x-icon')
    return HttpResponse(b"", status=200, content_type='image/x-icon')


def webmanifest_view(request):
    """
    Serves /site.webmanifest for PWA and Google mobile search engines with status 200 OK.
    """
    candidate = settings.BASE_DIR / 'static' / 'site.webmanifest'
    if candidate.is_file():
        content = candidate.read_text(encoding='utf-8')
        return HttpResponse(content, content_type='application/manifest+json')
    return HttpResponse('{"name":"NEONDROP"}', content_type='application/manifest+json')


def google_verification_file_view(request):
    """
    Handles Google Search Console HTML verification file request for /googlea35031ec8cebfe94.html.
    CRITICAL SECURITY REQUIREMENT:
    Strictly returns HTTP 200 ONLY for the exact authorized verification file.
    Does NOT dynamically spoof or generate tokens for arbitrary requests,
    which satisfies Google's anti-tampering and anti-hack canary verification checks.
    """
    file_path = settings.BASE_DIR / 'googlea35031ec8cebfe94.html'
    if file_path.is_file():
        content = file_path.read_text(encoding='utf-8').strip()
    else:
        content = "google-site-verification: googlea35031ec8cebfe94.html"
    return HttpResponse(content, content_type="text/html; charset=utf-8")



