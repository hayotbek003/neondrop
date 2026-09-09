import os
from django.conf import settings


def seo_context(request):
    """
    Provides global SEO variables for templates:
    - Absolute HTTPS canonical URL (clean path without filter/tracking query params)
    - Base site domain and absolute HTTPS site URL
    - Default Open Graph image
    - Google Search Console site verification code
    """
    site_domain = getattr(settings, 'SITE_DOMAIN', os.environ.get('SITE_DOMAIN', 'neondrop-ujly.onrender.com')).strip('/')
    site_url = f"https://{site_domain}"

    # Clean path without query parameters for canonical URL
    clean_path = request.path
    canonical_url = f"{site_url}{clean_path}"

    default_og_image = f"{site_url}/static/images/brand-logo.png"
    google_site_verification = getattr(
        settings,
        'GOOGLE_SITE_VERIFICATION',
        os.environ.get('GOOGLE_SITE_VERIFICATION', '')
    )

    return {
        'site_domain': site_domain,
        'site_url': site_url,
        'canonical_url': canonical_url,
        'default_og_image': default_og_image,
        'google_site_verification': google_site_verification,
    }
