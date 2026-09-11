import xml.etree.ElementTree as ET
import json
from django.test import TestCase, Client
from cases.models import Case, Item, CaseItem


class SEOTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Find or create an active case
        self.case = Case.objects.filter(active=True).first()
        if not self.case:
            self.case = Case.objects.create(
                name="SEO Test Case",
                slug="seo-test-case",
                price=50,
                active=True,
                color_theme="purple",
            )
        # Ensure at least one item in case
        if not self.case.case_items.exists():
            item = Item.objects.create(
                name="SEO Test Skin",
                weapon_type="AKM",
                skin_name="Neon Tiger",
                rarity="mythic",
                value=150,
            )
            CaseItem.objects.create(case=self.case, item=item, probability=100.0)

    def test_robots_txt(self):
        """Verify robots.txt is accessible, correctly formatted, and contains sitemap & disallow rules."""
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])
        content = response.content.decode('utf-8')
        
        self.assertIn('User-agent: *', content)
        self.assertIn('Allow: /', content)
        self.assertIn('Disallow: /admin/', content)
        self.assertIn('Disallow: /users/profile/', content)
        self.assertIn('Disallow: /inventory/', content)
        self.assertIn('Disallow: /api/', content)
        self.assertIn('Sitemap: https://', content)
        self.assertIn('/sitemap.xml', content)

    def test_sitemap_xml(self):
        """Verify sitemap.xml returns valid XML with absolute HTTPS URLs for all public pages and active cases."""
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertTrue('xml' in response['Content-Type'])
        
        root = ET.fromstring(response.content)
        # XML namespace for sitemaps
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [elem.text for elem in root.findall('ns:url/ns:loc', namespace)]
        
        self.assertTrue(len(urls) >= 4)
        for url in urls:
            self.assertTrue(url.startswith('https://'), f"URL does not start with https://: {url}")
            self.assertIn('neondrop-ujly.onrender.com', url)
            
        # Verify static pages are present
        urls_joined = " ".join(urls)
        self.assertIn('/', urls_joined)
        self.assertIn('/cases/', urls_joined)
        self.assertIn('/fairness/', urls_joined)
        self.assertIn('/top/', urls_joined)
        
        # Verify active case is present
        self.assertIn(f'/cases/{self.case.slug}/', urls_joined)

    def test_google_site_verification_file(self):
        """Verify googlea35031ec8cebfe94.html responds with 200 and fake tokens respond with 404."""
        response = self.client.get('/googlea35031ec8cebfe94.html')
        self.assertEqual(response.status_code, 200)
        self.assertTrue('text/html' in response['Content-Type'])
        self.assertEqual(response.content.decode('utf-8').strip(), "google-site-verification: googlea35031ec8cebfe94.html")

        # Security & Google anti-abuse canary check: Non-existent verification files MUST return 404
        fake_response = self.client.get('/googleFakeCanary12345.html')
        self.assertEqual(fake_response.status_code, 404)

    def test_yandex_site_verification_file(self):
        """Verify yandex verification HTML files respond with 200 and exact verification content."""
        # Current active token: f632a746318b12ac (GET without slash)
        response = self.client.get('/yandex_f632a746318b12ac.html')
        self.assertEqual(response.status_code, 200)
        self.assertTrue('text/html' in response['Content-Type'])
        content = response.content.decode('utf-8')
        self.assertIn('Verification: f632a746318b12ac', content)
        self.assertIn('<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">', content)

        # GET with trailing slash
        response_slash = self.client.get('/yandex_f632a746318b12ac.html/')
        self.assertEqual(response_slash.status_code, 200)
        self.assertIn('Verification: f632a746318b12ac', response_slash.content.decode('utf-8'))

        # HEAD request
        response_head = self.client.head('/yandex_f632a746318b12ac.html')
        self.assertEqual(response_head.status_code, 200)
        self.assertTrue('text/html' in response_head['Content-Type'])

        # Legacy token: b0735899c24f45c0
        response_old = self.client.get('/yandex_b0735899c24f45c0.html')
        self.assertEqual(response_old.status_code, 200)
        self.assertTrue('text/html' in response_old['Content-Type'])
        self.assertIn('Verification: b0735899c24f45c0', response_old.content.decode('utf-8'))

        # Security check: Non-existent verification files MUST return 404
        fake_response = self.client.get('/yandex_fake_canary12345.html')
        self.assertEqual(fake_response.status_code, 404)



    def test_homepage_seo(self):
        """Verify homepage has unique title, description, canonical, open graph, and valid Schema.org."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        self.assertIn('<title>NEONDROP — Честное открытие кейсов | Топовые скины и суперкары</title>', content)
        self.assertIn('<meta name="description"', content)
        self.assertIn('link rel="canonical" href="https://neondrop-ujly.onrender.com/"', content)
        self.assertIn('property="og:title"', content)
        self.assertIn('property="og:image"', content)
        self.assertIn('property="og:url" content="https://neondrop-ujly.onrender.com/"', content)
        self.assertIn('name="twitter:card" content="summary_large_image"', content)
        
        # Schema.org check
        self.assertIn('application/ld+json', content)
        self.assertIn('"@type": "WebSite"', content)
        self.assertIn('"@type": "Organization"', content)

    def test_cases_catalog_seo(self):
        """Verify cases catalog has unique title, description, canonical, and Schema.org CollectionPage."""
        response = self.client.get('/cases/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        self.assertIn('<title>Кейсы NEONDROP — Каталог кейсов с легендарными скинами и машинами</title>', content)
        self.assertIn('link rel="canonical" href="https://neondrop-ujly.onrender.com/cases/"', content)
        self.assertIn('"@type": "CollectionPage"', content)
        self.assertIn('"@type": "ItemList"', content)

    def test_case_detail_seo_and_ssr(self):
        """Verify case detail page has unique title, product schema, item chances, and SSR content."""
        response = self.client.get(f'/cases/{self.case.slug}/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Title and Canonical
        self.assertIn(f'{self.case.name} — кейс за', content)
        self.assertIn(f'Открой кейс «{self.case.name}» на NEONDROP за', content)
        self.assertIn(f'link rel="canonical" href="https://neondrop-ujly.onrender.com/cases/{self.case.slug}/"', content)
        
        # Meta and Open Graph
        self.assertIn('property="og:type" content="product"', content)
        self.assertIn('property="og:title"', content)
        
        # Schema.org Product, Breadcrumbs, ItemList
        self.assertIn('"@type": "Product"', content)
        self.assertIn('"@type": "BreadcrumbList"', content)
        self.assertIn('"@type": "ItemList"', content)
        
        # SSR content: Items, chances and prices rendered directly in HTML
        first_case_item = self.case.case_items.first()
        if first_case_item:
            self.assertIn(first_case_item.item.name, content)
            self.assertIn(first_case_item.item.weapon_type, content)
        
        # SSR SEO section
        self.assertIn(f'О КЕЙСЕ {self.case.name.upper()}', content)
        self.assertIn('Provably Fair', content)

    def test_provably_fair_page_seo(self):
        """Verify Provably Fair page SEO tags and TechArticle schema."""
        response = self.client.get('/fairness/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        self.assertIn('Честный серверный рандом Provably Fair (SHA-256) | NEONDROP', content)
        self.assertIn('link rel="canonical" href="https://neondrop-ujly.onrender.com/fairness/"', content)
        self.assertIn('"@type": "TechArticle"', content)

    def test_top_page_seo(self):
        """Verify Top Players page SEO tags."""
        response = self.client.get('/top/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        self.assertIn('Топ игроков и таблица лидеров | NEONDROP', content)
        self.assertIn('link rel="canonical" href="https://neondrop-ujly.onrender.com/top/"', content)

    def test_auth_pages_seo(self):
        """Verify login and register pages have titles and descriptions."""
        login_resp = self.client.get('/users/login/')
        self.assertEqual(login_resp.status_code, 200)
        self.assertIn('Вход в аккаунт | NEONDROP', login_resp.content.decode('utf-8'))
        
        reg_resp = self.client.get('/users/register/')
        self.assertEqual(reg_resp.status_code, 200)
        self.assertIn('Регистрация аккаунта | NEONDROP', reg_resp.content.decode('utf-8'))

    def test_no_accidental_noindex_on_public_pages(self):
        """Ensure that none of the public indexing targets contain a noindex directive."""
        endpoints = ['/', '/cases/', f'/cases/{self.case.slug}/', '/fairness/', '/top/']
        for ep in endpoints:
            res = self.client.get(ep)
            self.assertEqual(res.status_code, 200)
            self.assertNotIn('noindex', res.content.decode('utf-8').lower(), f"Unexpected noindex found on {ep}")

    def test_inactive_case_excluded_from_sitemap(self):
        """Verify inactive cases are strictly excluded from sitemap.xml."""
        inactive_case = Case.objects.create(
            name="Hidden Inactive Case",
            slug="hidden-inactive-case",
            price=999,
            active=False,
            color_theme="purple",
        )
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertNotIn(f'/cases/{inactive_case.slug}/', content)

    def test_favicon_ico_endpoint(self):
        """Verify /favicon.ico returns 200 OK and valid image/x-icon content for Googlebot."""
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 200)
        self.assertIn('image/x-icon', response['Content-Type'])
        self.assertTrue(len(response.content) > 0)

    def test_site_webmanifest_endpoint(self):
        """Verify /site.webmanifest returns 200 OK, valid JSON, and contains standard icon sizes."""
        response = self.client.get('/site.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/manifest+json', response['Content-Type'])
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data.get('name'), 'NEONDROP')
        self.assertTrue(len(data.get('icons', [])) > 0)
        sizes = [icon.get('sizes') for icon in data.get('icons', [])]
        self.assertIn('48x48', sizes)
        self.assertIn('96x96', sizes)
        self.assertIn('192x192', sizes)

    def test_favicon_tags_in_base_template(self):
        """Verify base HTML template includes Google Search compliant multi-resolution favicon tags."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('rel="icon" type="image/x-icon" href="/favicon.ico"', content)
        self.assertIn('rel="icon" type="image/png" sizes="48x48"', content)
        self.assertIn('rel="icon" type="image/png" sizes="96x96"', content)
        self.assertIn('rel="icon" type="image/png" sizes="192x192"', content)
        self.assertIn('rel="apple-touch-icon"', content)
        self.assertIn('rel="manifest" href="/site.webmanifest"', content)

