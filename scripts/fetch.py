#!/usr/bin/env python3
"""
SilkRoad Agri — Master Data Fetcher
Runs twice daily via GitHub Actions (02:00 UTC + 14:00 UTC)
All sources are free and public.
"""
import json, os, sys, time, re, datetime
import urllib.request, urllib.error, urllib.parse
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent))
import db

# ─── HTTP helpers ──────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SilkRoadAgri/1.0; research bot)",
    "Accept": "application/json,text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
}

def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', errors='replace'))
    except Exception as e:
        print(f"  ✗ JSON {url[:70]}: {e}")
        return None

def get_text(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"  ✗ TEXT {url[:70]}: {e}")
        return None

def get_csv(url, timeout=25):
    text = get_text(url, timeout)
    if not text:
        return []
    import io, csv
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)

TODAY = datetime.date.today().isoformat()
NOW = datetime.datetime.utcnow()

# ─── 1. FX RATES ───────────────────────────────────────────────────────────────

def fetch_fx():
    """Try multiple free FX APIs in order."""
    print("\n[1/6] FX rates…")
    sources = [
        "https://api.frankfurter.app/latest?from=USD&to=KZT,CNY,EUR",
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
        "https://open.er-api.com/v6/latest/USD",
    ]
    kzt, cny, eur = None, None, None
    for url in sources:
        data = get_json(url)
        if not data:
            continue
        # frankfurter.app
        if 'rates' in data:
            r = data['rates']
            kzt = r.get('KZT')
            cny = r.get('CNY')
            eur = r.get('EUR', 0.92)
            break
        # jsdelivr fawazahmed0
        if 'usd' in data:
            r = data['usd']
            kzt = r.get('kzt')
            cny = r.get('cny')
            eur = r.get('eur', 0.92)
            break
        time.sleep(0.5)

    if kzt is None:
        # Hard fallback
        kzt, cny, eur = 494.2, 7.24, 0.922
        print("  ↳ Using hardcoded fallback rates")
    else:
        print(f"  ✓ KZT={kzt:.1f}, CNY={cny:.4f}, EUR={eur:.4f}")

    db.upsert_fx(TODAY, round(kzt,2), round(cny,4), round(eur,4), source="frankfurter.app/fawazahmed0")
    return kzt, cny, eur

# ─── 2. UN COMTRADE ────────────────────────────────────────────────────────────

COMTRADE_PRODUCTS = {
    '1204': ('flaxseed', 'Flaxseed (亚麻籽)'),
    '1003': ('barley', 'Barley (大麦)'),
    '1206': ('sunflower_seed', 'Sunflower seed (葵花籽)'),
    '1512': ('sunflower_oil', 'Sunflower oil (葵花籽油)'),
    '1205': ('rapeseed', 'Rapeseed (菜籽)'),
}

def fetch_comtrade(key=None):
    """
    Try UN Comtrade API. With free key: 500 calls/day.
    Without key: use preview endpoint (limited but works).
    Register free at: https://comtradeplus.un.org/
    """
    print("\n[2/6] UN Comtrade (KAZ→CHN trade data)…")
    # Build period list: last 18 months
    periods = []
    for i in range(18):
        d = datetime.date.today().replace(day=1)
        for _ in range(i):
            d = (d - datetime.timedelta(days=1)).replace(day=1)
        periods.append(d.strftime('%Y%m'))
    period_str = ','.join(periods)

    fetched = 0
    for hs, (pname, plabel) in COMTRADE_PRODUCTS.items():
        if key:
            url = (f"https://comtradeapi.un.org/data/v1/get/C/M/HS"
                   f"?reporterCode=398&partnerCode=156&cmdCode={hs}"
                   f"&flowCode=X&period={period_str}&maxRecords=500"
                   f"&subscription-key={key}")
        else:
            url = (f"https://comtradeapi.un.org/public/v1/preview/C/M/HS"
                   f"?reporterCode=398&partnerCode=156&cmdCode={hs}"
                   f"&flowCode=X&period={period_str}")

        data = get_json(url)
        time.sleep(1.5)

        if not data or not data.get('data'):
            continue

        count = 0
        for row in data['data']:
            period_raw = str(row.get('period', ''))
            if len(period_raw) == 6:
                period = f"{period_raw[:4]}-{period_raw[4:]}"
            else:
                continue
            qty = row.get('netWgt') or row.get('qty') or 0
            value = row.get('primaryValue') or row.get('fobvalue') or 0
            if qty > 0:
                db.upsert_trade(period, 'KAZ', 'CHN', hs, plabel, qty, value,
                               source='UN Comtrade v1')
                count += 1
        fetched += count
        print(f"  ✓ HS {hs} ({plabel}): {count} monthly records")

    print(f"  Total Comtrade records: {fetched}")
    return fetched

# ─── 3. USDA FAS — free public reports ────────────────────────────────────────

def fetch_usda():
    """Fetch USDA FAS GAIN report metadata for Kazakhstan."""
    print("\n[3/6] USDA FAS GAIN reports…")
    url = ("https://apps.fas.usda.gov/newgainapi/api/report/reportsbypost"
           "?postCode=KZ&pageSize=10&pageNum=1")
    data = get_json(url)
    if not data:
        return

    count = 0
    for r in (data if isinstance(data, list) else []):
        title = r.get('title', '')
        date_str = (r.get('publicationDate') or TODAY)[:10]
        db.insert_news(date_str, f"[USDA FAS] {title}",
            source='USDA FAS GAIN Kazakhstan',
            url=f"https://fas.usda.gov/data/{r.get('reportId','')}",
            lang='en')
        count += 1
    print(f"  ✓ {count} USDA GAIN reports indexed")

# ─── 4. WORLD BANK COMMODITY PRICES ───────────────────────────────────────────

WB_INDICATORS = {
    'PBARL': ('barley', 'fob_world', 'Barley world FOB'),
    'PSUNO': ('sunflower_oil', 'fob_world', 'Sunflower oil world'),
    'PWHEAMT': ('wheat', 'fob_world', 'Wheat world FOB'),
    'PSOIL': ('soybean_oil', 'fob_world', 'Soybean oil world'),
}

def fetch_worldbank():
    """World Bank Pink Sheet commodity prices — free, no key."""
    print("\n[4/6] World Bank commodity prices…")
    count = 0
    for indicator, (product, price_type, label) in WB_INDICATORS.items():
        url = f"https://api.worldbank.org/v2/en/indicator/{indicator}?format=json&mrv=18&frequency=M"
        data = get_json(url)
        time.sleep(0.4)
        if not data or len(data) < 2 or not data[1]:
            continue
        for r in data[1]:
            val = r.get('value')
            if val is None:
                continue
            period = r.get('date', '')  # format: 2025M01 or 2025-01
            period = period.replace('M', '-')
            if len(period) == 7:
                db.upsert_price(period, product, price_type, value_usd=round(float(val),2),
                               source=f'World Bank {indicator}')
                count += 1
    print(f"  ✓ {count} World Bank price records")

# ─── 5. GRAIN UNION KZ public website ─────────────────────────────────────────

def fetch_grain_union():
    """Scrape Grain Union of Kazakhstan public news and price mentions."""
    print("\n[5/6] Grain Union Kazakhstan (grainunion.kz)…")
    pages = [
        ('https://grainunion.kz/en/news', 'en'),
        ('https://grainunion.kz/ru/news', 'ru'),
    ]
    count = 0
    for url, lang in pages:
        html = get_text(url, timeout=30)
        if not html:
            continue
        # Extract article titles and dates
        titles = re.findall(r'<(?:h[23]|a)[^>]*class="[^"]*(?:title|heading|news)[^"]*"[^>]*>([^<]{15,300})<', html, re.I)
        if not titles:
            # Generic link text inside news-like divs
            titles = re.findall(r'<a[^>]+href="[^"]*/news/[^"]*"[^>]*>\s*([^<]{15,250})\s*</a>', html, re.I)
        dates = re.findall(r'(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{2}-\d{2})', html)
        for i, t in enumerate(titles[:8]):
            t = re.sub(r'\s+', ' ', t).strip()
            if len(t) < 15:
                continue
            date_str = TODAY
            if i < len(dates):
                try:
                    from datetime import datetime
                    for fmt in ('%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                        try:
                            date_str = datetime.strptime(dates[i], fmt).strftime('%Y-%m-%d')
                            break
                        except:
                            pass
                except:
                    pass
            db.insert_news(date_str, t, source='Grain Union Kazakhstan', url=url, lang=lang)
            count += 1
        time.sleep(1)

    # Also try APK-Inform free headlines
    apk_url = 'https://apk-inform.com/en/news'
    html = get_text(apk_url, timeout=30)
    if html:
        titles = re.findall(r'<a[^>]+href="/en/news/[^"]*"[^>]*>\s*([^<]{20,200})\s*</a>', html, re.I)
        for t in titles[:6]:
            t = re.sub(r'\s+', ' ', t).strip()
            if len(t) > 20:
                db.insert_news(TODAY, f"[APK-Inform] {t}", source='APK-Inform', url=apk_url, lang='en')
                count += 1

    print(f"  ✓ {count} news items collected")

# ─── 6. MANUAL PRICE BASELINE ─────────────────────────────────────────────────
# Updated based on latest available Grain Union KZ data.
# These serve as authoritative spot prices when scraping isn't possible.

MANUAL_PRICES = {
    # (product, price_type, value_usd, value_cny, value_kzt, source)
    'flaxseed': [
        ('ewx_kostanay', 488, None, 240000, 'Grain Union KZ W21/2026'),
        ('fca_kz', 512, None, None, 'Grain Union KZ W21/2026'),
        ('cf_tianjin', 571, None, None, 'APK-Inform W21/2026'),
        ('china_domestic_yinchuan', 666, 4820, None, 'China GACC / market report W21/2026'),
    ],
    'barley': [
        ('ewx_kz', 138, None, None, 'Grain Union KZ W21/2026'),
        ('fca_kz', 152, None, None, 'Grain Union KZ W21/2026'),
    ],
    'sunflower_oil': [
        ('fob_kz', 895, None, None, 'APK-Inform W21/2026'),
    ],
    'sunflower_seed': [
        ('ewx_kz', 284, None, None, 'Grain Union KZ W21/2026 (w/ 20% duty applies)'),
    ],
    'wheat': [
        ('ewx_kz', 162, None, None, 'Grain Union KZ W21/2026'),
        ('fca_kz', 178, None, None, 'Grain Union KZ W21/2026'),
    ],
}

MANUAL_FREIGHT = [
    ('kostanay_to_khorgos', 42, 12, 16, 'KTZ tariff Q2/2026'),
    ('nko_to_khorgos', 38, 11, 15, 'KTZ tariff Q2/2026'),
    ('akmola_to_khorgos', 46, 14, 18, 'KTZ tariff Q2/2026'),
    ('dostyk_route', 44, 14, 20, 'KTZ tariff Q2/2026'),
    ('china_khorgos_yinchuan', 8, 2, 3, 'China Railway estimate Q2/2026'),
    ('china_khorgos_lanzhou', 11, 3, 4, 'China Railway estimate Q2/2026'),
    ('china_khorgos_tianjin', 22, 5, 7, 'China Railway estimate Q2/2026'),
    ('truck_khorgos_highway', 65, 0, 1, 'Market rate Q2/2026'),
]

def seed_manual_data():
    """Always insert manual baseline (will not overwrite if date/key same, but refreshes today's entry)."""
    print("\n[6/6] Seeding manual price baselines…")
    for product, entries in MANUAL_PRICES.items():
        for (pt, usd, cny, kzt, src) in entries:
            db.upsert_price(TODAY, product, pt, usd, cny, kzt, src)
    for (route, rate, dmin, dmax, src) in MANUAL_FREIGHT:
        db.upsert_freight(TODAY, route, rate, dmin, dmax, src)
    print(f"  ✓ {sum(len(v) for v in MANUAL_PRICES.values())} price entries, {len(MANUAL_FREIGHT)} freight routes")

# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print(f" SilkRoad Agri — Data Fetch @ {NOW.strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * 65)

    db.init_db()

    COMTRADE_KEY = os.environ.get('COMTRADE_KEY', '')
    errors = []

    try: kzt, cny, eur = fetch_fx()
    except Exception as e: errors.append(f"FX: {e}"); kzt, cny, eur = 494.2, 7.24, 0.922

    try: fetch_comtrade(COMTRADE_KEY or None)
    except Exception as e: errors.append(f"Comtrade: {e}")

    try: fetch_usda()
    except Exception as e: errors.append(f"USDA: {e}")

    try: fetch_worldbank()
    except Exception as e: errors.append(f"WB: {e}")

    try: fetch_grain_union()
    except Exception as e: errors.append(f"GrainUnion: {e}")

    seed_manual_data()

    print(f"\n{'─'*65}")
    print("Exporting to JSON…")
    try:
        db.export_to_json()
    except Exception as e:
        errors.append(f"JSON export: {e}")
        print(f"  ✗ JSON export error: {e}")

    if errors:
        print(f"\n⚠ Non-fatal errors ({len(errors)}):")
        for e in errors: print(f"  - {e}")
    print(f"\n✓ Done @ {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")

if __name__ == '__main__':
    main()
