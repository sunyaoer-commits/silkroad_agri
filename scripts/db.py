"""
SilkRoad Agri — SQLite Database Manager
Stores all historical data. Runs locally and on GitHub Actions.
"""
import sqlite3, os, json
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'silkroad.db')

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # Spot prices table (daily snapshot)
    c.execute('''CREATE TABLE IF NOT EXISTS prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        product TEXT NOT NULL,
        price_type TEXT NOT NULL,
        value_usd REAL,
        value_cny REAL,
        value_kzt REAL,
        unit TEXT DEFAULT 'tonne',
        source TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(date, product, price_type)
    )''')
    # Trade flows (monthly, from UN Comtrade / China GACC)
    c.execute('''CREATE TABLE IF NOT EXISTS trade_flows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        reporter TEXT NOT NULL,
        partner TEXT NOT NULL,
        hs_code TEXT NOT NULL,
        product_name TEXT,
        flow TEXT DEFAULT 'export',
        qty_tonnes REAL,
        value_usd REAL,
        unit_price_usd REAL,
        source TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(period, reporter, partner, hs_code, flow)
    )''')
    # FX rates
    c.execute('''CREATE TABLE IF NOT EXISTS fx_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        kzt_per_usd REAL,
        cny_per_usd REAL,
        eur_per_usd REAL,
        source TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # Rail freight rates
    c.execute('''CREATE TABLE IF NOT EXISTS freight_rates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        route TEXT NOT NULL,
        usd_per_tonne REAL,
        transit_days_min INTEGER,
        transit_days_max INTEGER,
        source TEXT,
        UNIQUE(date, route)
    )''')
    # News / market intelligence
    c.execute('''CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pub_date TEXT,
        title TEXT NOT NULL,
        summary TEXT,
        source TEXT,
        url TEXT,
        lang TEXT DEFAULT 'en',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # Daily reports
    c.execute('''CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        title TEXT,
        content_md TEXT,
        content_html TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    print(f"✓ DB initialized at {DB_PATH}")

def upsert_price(date_str, product, price_type, value_usd=None, value_cny=None, value_kzt=None, source=None):
    conn = get_conn()
    conn.execute('''INSERT INTO prices (date, product, price_type, value_usd, value_cny, value_kzt, source)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(date,product,price_type) DO UPDATE SET
        value_usd=excluded.value_usd, value_cny=excluded.value_cny,
        value_kzt=excluded.value_kzt, source=excluded.source''',
        (date_str, product, price_type, value_usd, value_cny, value_kzt, source))
    conn.commit(); conn.close()

def upsert_trade(period, reporter, partner, hs_code, product_name, qty, value_usd, flow='export', source=None):
    unit_price = round(value_usd / qty, 2) if qty and qty > 0 and value_usd else None
    conn = get_conn()
    conn.execute('''INSERT INTO trade_flows
        (period, reporter, partner, hs_code, product_name, flow, qty_tonnes, value_usd, unit_price_usd, source)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(period,reporter,partner,hs_code,flow) DO UPDATE SET
        qty_tonnes=excluded.qty_tonnes, value_usd=excluded.value_usd,
        unit_price_usd=excluded.unit_price_usd, source=excluded.source''',
        (period, reporter, partner, hs_code, product_name, flow, qty, value_usd, unit_price, source))
    conn.commit(); conn.close()

def upsert_fx(date_str, kzt, cny, eur=None, source=None):
    conn = get_conn()
    conn.execute('''INSERT INTO fx_rates (date, kzt_per_usd, cny_per_usd, eur_per_usd, source)
        VALUES (?,?,?,?,?)
        ON CONFLICT(date) DO UPDATE SET
        kzt_per_usd=excluded.kzt_per_usd, cny_per_usd=excluded.cny_per_usd,
        eur_per_usd=excluded.eur_per_usd''',
        (date_str, kzt, cny, eur, source))
    conn.commit(); conn.close()

def upsert_freight(date_str, route, usd_per_tonne, days_min=None, days_max=None, source=None):
    conn = get_conn()
    conn.execute('''INSERT INTO freight_rates (date, route, usd_per_tonne, transit_days_min, transit_days_max, source)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(date,route) DO UPDATE SET
        usd_per_tonne=excluded.usd_per_tonne''',
        (date_str, route, usd_per_tonne, days_min, days_max, source))
    conn.commit(); conn.close()

def insert_news(pub_date, title, summary=None, source=None, url=None, lang='en'):
    conn = get_conn()
    # Check for duplicate by title
    exists = conn.execute('SELECT id FROM news WHERE title=?', (title,)).fetchone()
    if not exists:
        conn.execute('INSERT INTO news (pub_date, title, summary, source, url, lang) VALUES (?,?,?,?,?,?)',
            (pub_date, title, summary, source, url, lang))
        conn.commit()
    conn.close()

def save_report(date_str, title, content_md, content_html=None):
    conn = get_conn()
    conn.execute('''INSERT INTO reports (date, title, content_md, content_html)
        VALUES (?,?,?,?)
        ON CONFLICT(date) DO UPDATE SET
        title=excluded.title, content_md=excluded.content_md, content_html=excluded.content_html''',
        (date_str, title, content_md, content_html))
    conn.commit(); conn.close()

def query(sql, params=()):
    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_latest_prices():
    return query('''SELECT p.* FROM prices p
        INNER JOIN (SELECT product, price_type, MAX(date) as md FROM prices GROUP BY product, price_type) latest
        ON p.product=latest.product AND p.price_type=latest.price_type AND p.date=latest.md
        ORDER BY p.product, p.price_type''')

def get_price_history(product, price_type, months=18):
    return query('''SELECT date, value_usd, value_cny, source FROM prices
        WHERE product=? AND price_type=?
        AND date >= date('now',?) ORDER BY date''',
        (product, price_type, f'-{months} months'))

def get_trade_history(hs_code, reporter='KAZ', partner='CHN', months=24):
    return query('''SELECT period, qty_tonnes, value_usd, unit_price_usd, source
        FROM trade_flows
        WHERE hs_code=? AND reporter=? AND partner=?
        AND period >= strftime('%Y-%m', date('now',?))
        ORDER BY period''',
        (hs_code, reporter, partner, f'-{months} months'))

def get_recent_news(limit=10, lang=None):
    if lang:
        return query('SELECT * FROM news WHERE lang=? ORDER BY pub_date DESC, id DESC LIMIT ?', (lang, limit))
    return query('SELECT * FROM news ORDER BY pub_date DESC, id DESC LIMIT ?', (limit,))

def export_to_json():
    """Export DB snapshot to data/market_data.json for the frontend."""
    import json
    from datetime import datetime
    prices = get_latest_prices()
    news = get_recent_news(10)
    trade_flax = get_trade_history('1204', months=24)
    trade_barley = get_trade_history('1003', months=24)
    flax_hist = get_price_history('flaxseed', 'fca_kz', months=18)
    barley_hist = get_price_history('barley', 'fca_kz', months=18)
    oil_hist = get_price_history('sunflower_oil', 'fob', months=18)
    # FX
    fx_rows = query('SELECT * FROM fx_rates ORDER BY date DESC LIMIT 1')
    fx = fx_rows[0] if fx_rows else {'kzt_per_usd': 494.2, 'cny_per_usd': 7.24}
    # Spot prices dict
    sp = {}
    for p in prices:
        key = f"{p['product']}_{p['price_type'].replace('/','_')}"
        sp[key] = p['value_usd']
    # Freight
    freight = query('''SELECT route, usd_per_tonne, transit_days_min, transit_days_max
        FROM freight_rates WHERE date = (SELECT MAX(date) FROM freight_rates)''')
    freight_dict = {r['route']: r for r in freight}
    # Annual trade summary
    annual = query('''SELECT substr(period,1,4) as year,
        SUM(qty_tonnes) as total_tonnes, SUM(value_usd) as total_usd_m
        FROM trade_flows WHERE hs_code='1204' AND reporter='KAZ' AND partner='CHN'
        GROUP BY year ORDER BY year''')
    annual_dict = {r['year']: {'flaxseed_tonnes': int(r['total_tonnes'] or 0),
        'value_usd_m': round((r['total_usd_m'] or 0)/1e6, 1)} for r in annual}
    # Reports
    latest_report = query('SELECT date, title, content_md FROM reports ORDER BY date DESC LIMIT 1')
    output = {
        'meta': {
            'generated': datetime.utcnow().isoformat() + 'Z',
            'sources': ['UN Comtrade', 'Grain Union KZ', 'APK-Inform', 'USDA FAS', 'China GACC', 'KTZ tariff'],
            'db_records': {
                'prices': query('SELECT COUNT(*) as n FROM prices')[0]['n'],
                'trade_flows': query('SELECT COUNT(*) as n FROM trade_flows')[0]['n'],
                'news_items': query('SELECT COUNT(*) as n FROM news')[0]['n'],
            }
        },
        'fx': {'KZT_per_USD': fx.get('kzt_per_usd', 494.2), 'CNY_per_USD': fx.get('cny_per_usd', 7.24)},
        'spot_prices': sp,
        'price_history': {
            'flaxseed_fca': [{'period': r['date'], 'value': r['value_usd']} for r in flax_hist if r['value_usd']],
            'barley_fca': [{'period': r['date'], 'value': r['value_usd']} for r in barley_hist if r['value_usd']],
            'sunflower_oil_fob': [{'period': r['date'], 'value': r['value_usd']} for r in oil_hist if r['value_usd']],
        },
        'trade_flows': {
            'kz_china_flaxseed_monthly': [
                {'period': r['period'], 'volume_tonnes': int(r['qty_tonnes'] or 0),
                 'value_usd_m': round((r['value_usd'] or 0)/1e6, 2)}
                for r in trade_flax],
            'kz_china_barley_monthly': [
                {'period': r['period'], 'volume_tonnes': int(r['qty_tonnes'] or 0),
                 'value_usd_m': round((r['value_usd'] or 0)/1e6, 2)}
                for r in trade_barley],
            'annual_summary': annual_dict,
            'source': 'China GACC monthly + UN Comtrade HS 1204/1003',
        },
        'rail_freight': freight_dict or {
            'kostanay_to_khorgos': {'usd_per_tonne': 42, 'transit_days_min': 12, 'transit_days_max': 16},
            'nko_to_khorgos': {'usd_per_tonne': 38, 'transit_days_min': 11, 'transit_days_max': 15},
        },
        'news': [{'date': n['pub_date'], 'title': n['title'],
                  'summary': n.get('summary',''), 'source': n.get('source','')}
                 for n in news],
        'latest_report': latest_report[0] if latest_report else None,
    }
    out_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'market_data.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"✓ Exported market_data.json ({os.path.getsize(out_path):,} bytes)")
    return output

if __name__ == '__main__':
    init_db()
