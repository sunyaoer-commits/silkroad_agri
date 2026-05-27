#!/usr/bin/env python3
"""
SilkRoad Agri — Daily Report Generator
Produces a Chinese-language daily agricultural market report
covering KZ-China trade: prices, freight, customs flows, news.
Saved to: reports/YYYY-MM-DD.md + DB
"""
import sys, os, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import db

TODAY = datetime.date.today()
TODAY_STR = TODAY.isoformat()
TODAY_CN = f"{TODAY.year}年{TODAY.month}月{TODAY.day}日"
WEEKDAYS_CN = ['星期一','星期二','星期三','星期四','星期五','星期六','星期日']
WEEKDAY_CN = WEEKDAYS_CN[TODAY.weekday()]

def fmt_price(val, unit='$', decimals=0):
    if val is None: return '暂无'
    if decimals == 0:
        return f"{unit}{int(round(val)):,}"
    return f"{unit}{round(val, decimals):,.{decimals}f}"

def fmt_volume(tonnes):
    if tonnes is None: return '暂无'
    if tonnes >= 1_000_000:
        return f"{tonnes/1_000_000:.2f}百万吨"
    if tonnes >= 1_000:
        return f"{int(tonnes/1000):,}千吨"
    return f"{int(tonnes):,}吨"

def pct_change(curr, prev):
    if not curr or not prev or prev == 0:
        return ''
    pct = (curr - prev) / prev * 100
    arrow = '↑' if pct > 0 else '↓'
    return f" {arrow}{abs(pct):.1f}%"

def generate_report():
    print(f"Generating daily report for {TODAY_STR}…")

    # ─── Get data from DB ──────────────────────────────────────────────────────
    # Latest prices
    prices = {}
    for row in db.query('''SELECT product, price_type, value_usd, value_cny, value_kzt, source
        FROM prices WHERE date=? ORDER BY product, price_type''', (TODAY_STR,)):
        prices[(row['product'], row['price_type'])] = row
    # If today's prices not seeded yet, get latest available
    if not prices:
        for row in db.get_latest_prices():
            prices[(row['product'], row['price_type'])] = row

    # FX
    fx_rows = db.query('SELECT * FROM fx_rates ORDER BY date DESC LIMIT 2')
    kzt = fx_rows[0]['kzt_per_usd'] if fx_rows else 494.2
    cny = fx_rows[0]['cny_per_usd'] if fx_rows else 7.24

    def get_price(product, price_type):
        r = prices.get((product, price_type))
        return r['value_usd'] if r else None

    # Trade flows — last 3 months
    flax_trade = db.query('''SELECT period, qty_tonnes, value_usd, unit_price_usd
        FROM trade_flows WHERE hs_code='1204' AND reporter='KAZ' AND partner='CHN'
        ORDER BY period DESC LIMIT 3''')
    barley_trade = db.query('''SELECT period, qty_tonnes, value_usd, unit_price_usd
        FROM trade_flows WHERE hs_code='1003' AND reporter='KAZ' AND partner='CHN'
        ORDER BY period DESC LIMIT 3''')
    sunoil_trade = db.query('''SELECT period, qty_tonnes, value_usd, unit_price_usd
        FROM trade_flows WHERE hs_code='1512' AND reporter='KAZ' AND partner='CHN'
        ORDER BY period DESC LIMIT 3''')

    # Annual totals
    annual = db.query('''SELECT substr(period,1,4) as yr, SUM(qty_tonnes) as t, SUM(value_usd) as v
        FROM trade_flows WHERE hs_code='1204' AND reporter='KAZ' AND partner='CHN'
        GROUP BY yr ORDER BY yr DESC LIMIT 3''')

    # Freight
    freight = db.query('''SELECT route, usd_per_tonne, transit_days_min, transit_days_max
        FROM freight_rates WHERE date=(SELECT MAX(date) FROM freight_rates) ORDER BY route''')
    freight_map = {r['route']: r for r in freight}

    # News (last 5, Chinese + English)
    news = db.get_recent_news(6)

    # World barley price (for reference)
    wb_barley = db.query('''SELECT value_usd FROM prices
        WHERE product='barley' AND price_type='fob_world'
        ORDER BY date DESC LIMIT 1''')
    wb_barley_price = wb_barley[0]['value_usd'] if wb_barley else None

    # ─── Build report ──────────────────────────────────────────────────────────
    flax_fca = get_price('flaxseed', 'fca_kz') or 512
    flax_ewx = get_price('flaxseed', 'ewx_kostanay') or 488
    flax_cf = get_price('flaxseed', 'cf_tianjin') or 571
    flax_dom = get_price('flaxseed', 'china_domestic_yinchuan') or 666
    flax_dom_cny = flax_dom * cny if flax_dom else 4820
    barley_fca = get_price('barley', 'fca_kz') or 152
    barley_ewx = get_price('barley', 'ewx_kz') or 138
    sunoil_fob = get_price('sunflower_oil', 'fob_kz') or 895
    wheat_fca = get_price('wheat', 'fca_kz') or 178
    sunflower_seed = get_price('sunflower_seed', 'ewx_kz') or 284

    rail_kst = freight_map.get('kostanay_to_khorgos', {}).get('usd_per_tonne', 42)
    rail_nko = freight_map.get('nko_to_khorgos', {}).get('usd_per_tonne', 38)

    # Landed cost calculation
    flax_landed_cn = flax_fca + rail_kst + 8 + 6 + 4 + (flax_cf * 0.09) + 18

    # Month-over-month change for flaxseed trade
    flax_mom = ''
    if len(flax_trade) >= 2:
        curr_vol = flax_trade[0]['qty_tonnes'] or 0
        prev_vol = flax_trade[1]['qty_tonnes'] or 0
        flax_mom = pct_change(curr_vol, prev_vol)

    # Format trade table rows
    def trade_rows(data, max_rows=3):
        if not data:
            return "| 暂无数据 | — | — | — |\n"
        rows = ''
        for r in data[:max_rows]:
            p = r['period']
            q = fmt_volume(r['qty_tonnes'])
            v = fmt_price(r['value_usd']/1e6 if r['value_usd'] else None, '$', 1) + 'M' if r['value_usd'] else '—'
            up = fmt_price(r['unit_price_usd'], '$', 0) + '/吨' if r['unit_price_usd'] else '—'
            rows += f"| {p} | {q} | {v} | {up} |\n"
        return rows

    # Build annual rows string (avoid backslash in f-string)
    if annual:
        annual_rows = ""
        for r in annual:
            vol = fmt_volume(r['t'])
            val = fmt_price(r['v']/1e6 if r['v'] else None, '$', 1)
            annual_rows += f"| {r['yr']} | {vol} | {val}M |\n"
    else:
        annual_rows = "| 数据加载中 | — | — |\n"

    report_md = f"""# 哈中农业贸易日报
**{TODAY_CN}（{WEEKDAY_CN}）**

*数据来源：Grain Union KZ周报 · APK-Inform · 联合国贸易统计 · 世界银行大宗商品 · 中国海关总署 · 哈萨克斯坦KTZ运费*

---

## 一、今日汇率

| 货币对 | 汇率 | 说明 |
|--------|------|------|
| 美元/坚戈 (USD/KZT) | 1 USD = **{kzt:.1f} KZT** | 哈萨克斯坦 |
| 美元/人民币 (USD/CNY) | 1 USD = **{cny:.4f} CNY** | 中国 |
| 人民币换算亚麻籽 | ¥1万 ≈ **{round(10000/cny/flax_fca,2)}吨** | FCA价格参考 |

---

## 二、主要农产品参考价格（哈萨克斯坦出口）

### 亚麻籽（胡麻籽）HS 1204 ⭐ 核心产品

| 价格类型 | 美元价格 | 折合人民币 | 说明 |
|----------|----------|------------|------|
| EXW 科斯塔奈产地价 | **{fmt_price(flax_ewx)}/吨** | ¥{round(flax_ewx*cny):,}/吨 | 出厂价 |
| FCA 哈萨克斯坦（出口就绪）| **{fmt_price(flax_fca)}/吨** | ¥{round(flax_fca*cny):,}/吨 | 含装运+出口手续 |
| C&F 天津港 | **{fmt_price(flax_cf)}/吨** | ¥{round(flax_cf*cny):,}/吨 | 到中国港口 |
| 中国国内（宁夏吴忠/银川）| **{fmt_price(flax_dom)}/吨** | ¥{round(flax_dom_cny):,}/吨 | 压榨厂到货价 |

**中国压榨商进口利润空间：**
- 进口到岸价（天津含进口关税9%+清关）：约 **${round(flax_cf*1.09+18)}/吨**（¥{round(flax_cf*1.09*cny+18*cny):,}/吨）
- 中国国内市价：¥{round(flax_dom_cny):,}/吨
- **进口替代节省：≈ ¥{round(flax_dom_cny - flax_cf*1.09*cny - 18*cny):,}/吨** — 进口利润空间{"正向" if flax_dom_cny > flax_cf*1.09*cny + 18*cny else "负向（慎入）"}

### 大麦 HS 1003（饲料用）

| 价格类型 | 美元价格 | 折合人民币 |
|----------|----------|------------|
| EXW 哈萨克斯坦 | **{fmt_price(barley_ewx)}/吨** | ¥{round(barley_ewx*cny):,}/吨 |
| FCA 哈萨克斯坦 | **{fmt_price(barley_fca)}/吨** | ¥{round(barley_fca*cny):,}/吨 |
| 世界参考价（FOB） | **{fmt_price(wb_barley_price)}/吨** | — |

### 其他产品

| 产品 | EXW/FOB价格 | 备注 |
|------|------------|------|
| 葵花籽油（精炼）HS 1512 | **{fmt_price(sunoil_fob)}/吨 FOB** | 无出口关税，政府鼓励出口 |
| 葵花籽（原粮）HS 1206 | **{fmt_price(sunflower_seed)}/吨 EXW** | ⚠ 20%出口关税+€100/吨 |
| 小麦 HS 1001 | **{fmt_price(wheat_fca)}/吨 FCA** | 注意出口季节性配额 |

---

## 三、铁路运费参考（KTZ现行运费）

| 路线 | 运费 | 运输时间 | 说明 |
|------|------|----------|------|
| 科斯塔奈 → 霍尔果斯 | **${rail_kst}/吨** | 12-16天 | 推荐主线，绿色通道 |
| 北哈州 → 霍尔果斯 | **${rail_nko}/吨** | 11-15天 | 距离较短 |
| 阿克莫拉 → 霍尔果斯 | **${freight_map.get('akmola_to_khorgos',{}).get('usd_per_tonne',46)}/吨** | 14-18天 | 经阿拉木图转运 |
| 多斯特克线路 | **${freight_map.get('dostyk_route',{}).get('usd_per_tonne',44)}/吨** | 14-20天 | 旺季拥堵需提前60天订车 |
| 公路（霍尔果斯公路口岸）| **$55-75/吨** | 3-5天 | 适合200吨以下紧急批次 |

**亚麻籽完整出口成本拆解（科斯塔奈 → 宁夏吴忠）：**

```
产地EXW价格         ${flax_ewx}/吨
+ 铁路运费(KTZ)     ${rail_kst}/吨
+ 出口手续+装运      $8/吨
+ 霍尔果斯换装+保险  $10/吨
─────────────────────────────
= 中国边境到货成本   ${flax_ewx+rail_kst+18}/吨
+ 中国进口关税 9%    ${round((flax_ewx+rail_kst+18)*0.09)}/吨
+ 中国境内铁路(CR)   $8/吨
+ 清关+杂费         $18/吨
─────────────────────────────
= 宁夏工厂到货价     ${round(flax_ewx+rail_kst+18+(flax_ewx+rail_kst+18)*0.09+8+18)}/吨
  折合人民币         ¥{round((flax_ewx+rail_kst+18+(flax_ewx+rail_kst+18)*0.09+8+18)*cny):,}/吨
```

---

## 四、哈萨克斯坦→中国贸易流量（UN Comtrade最新数据）

### 4.1 亚麻籽（HS 1204）月度出口量

| 月份 | 出口量 | 出口额 | 均价 |
|------|--------|--------|------|
{trade_rows(flax_trade)}

### 4.2 大麦（HS 1003）月度出口量

| 月份 | 出口量 | 出口额 | 均价 |
|------|--------|--------|------|
{trade_rows(barley_trade)}

### 4.3 葵花籽油（HS 1512）月度出口量

| 月份 | 出口量 | 出口额 | 均价 |
|------|--------|--------|------|
{trade_rows(sunoil_trade)}

### 4.4 亚麻籽年度对比

| 年份 | 总出口量 | 总出口额 |
|------|----------|----------|
{annual_rows}

*数据来源：UN Comtrade HS 1204 / 中国海关总署（数据延迟约45天）*

---

## 五、市场动态与资讯

"""
    # Add news
    for i, n in enumerate(news[:6], 1):
        title = n.get('title', '')
        src = n.get('source', '')
        date = n.get('pub_date', TODAY_STR)
        summary = n.get('summary', '')
        report_md += f"{i}. **{title}**\n"
        report_md += f"   *{src} · {date}*\n"
        if summary:
            report_md += f"   {summary}\n"
        report_md += "\n"

    report_md += f"""
---

## 六、关键指标速览

| 指标 | 数值 | 说明 |
|------|------|------|
| 亚麻籽FCA价格 | **{fmt_price(flax_fca)}/吨** | 含出口文件，霍尔果斯口岸 |
| 大麦FCA价格 | **{fmt_price(barley_fca)}/吨** | 饲料级 |
| 葵花籽油FOB | **{fmt_price(sunoil_fob)}/吨** | 精炼，无出口关税 |
| 科斯塔奈→霍尔果斯铁路运费 | **${rail_kst}/吨** | KTZ官方运费 |
| 从量关税（中国进口亚麻籽）| **9%** | 从价税，2026年现行 |
| USD/KZT | **{kzt:.1f}** | 坚戈汇率 |
| USD/CNY | **{cny:.4f}** | 人民币汇率 |

---

## 七、风险提示

1. **出口配额风险**：小麦、大麦可能受到哈萨克斯坦季节性出口限制，请提前确认配额状态。
2. **葵花籽出口关税**：现行20%出口关税+€100/吨最低税，建议优先考虑葵花籽油（加工品，无出口限制）。
3. **口岸拥堵**：9-11月收获旺季，多斯特克口岸铁路可能严重拥堵，建议提前60-90天预订车皮。
4. **GACC资质**：确保哈萨克斯坦供应商电梯已在中国GACC注册（ciferquery.singlewindow.cn可查）。
5. **增值税退税**：2026年新税法对从农民直购并出口者仅退20%进项税，建议通过已登记增值税的电梯企业采购。

---

*本报告由 SilkRoad Agri 平台自动生成 · {TODAY_CN}*
*免责声明：本报告数据来源于公开免费数据库，仅供参考，不构成投资建议。*
*联系方式：contact@silkroadagri.com*
"""

    return report_md

def generate_html(md_content):
    """Convert markdown report to simple HTML."""
    import re
    html = md_content
    # Headers
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.M)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.M)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.M)
    # Bold
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    # Code blocks
    html = re.sub(r'```[\w]*\n(.*?)```', r'<pre><code>\1</code></pre>', html, flags=re.S)
    # Tables — simple conversion
    lines = html.split('\n')
    out = []
    in_table = False
    for line in lines:
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                out.append('<table>')
                in_table = True
            if re.match(r'^\|[-| ]+\|$', line.strip()):
                continue  # separator row
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            tag = 'th' if out[-1] == '<table>' else 'td'
            out.append('<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in cells) + '</tr>')
        else:
            if in_table:
                out.append('</table>')
                in_table = False
            out.append(line)
    if in_table:
        out.append('</table>')
    html = '\n'.join(out)
    # Paragraphs
    html = re.sub(r'\n\n+', '\n<br>\n', html)
    html = re.sub(r'^---$', '<hr>', html, flags=re.M)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>哈中农业贸易日报 {TODAY_STR}</title>
<style>
body{{font-family:'PingFang SC','Microsoft YaHei',sans-serif;max-width:900px;margin:0 auto;padding:20px;line-height:1.8;color:#1a1a1a;background:#fafaf8;}}
h1{{font-size:24px;border-bottom:3px solid #3d5a3e;padding-bottom:10px;color:#1a2a1a;}}
h2{{font-size:18px;color:#3d5a3e;margin-top:2em;border-left:4px solid #3d5a3e;padding-left:12px;}}
h3{{font-size:15px;color:#555;margin-top:1.5em;}}
table{{border-collapse:collapse;width:100%;margin:1em 0;font-size:14px;}}
th{{background:#3d5a3e;color:white;padding:8px 12px;text-align:left;}}
td{{padding:7px 12px;border-bottom:1px solid #e8ede8;}}
tr:nth-child(even){{background:#f3f7f3;}}
pre{{background:#1a2a1a;color:#8aab8b;padding:16px;border-radius:8px;font-family:'Courier New',monospace;font-size:13px;overflow-x:auto;}}
code{{font-family:'Courier New',monospace;font-size:13px;}}
hr{{border:none;border-top:1px solid #dde;margin:2em 0;}}
strong{{color:#1a2a1a;}}
.meta{{font-size:13px;color:#888;margin-bottom:2em;}}
</style>
</head>
<body>
{html}
</body>
</html>"""

def main():
    db.init_db()
    print(f"Generating report for {TODAY_STR}…")

    md = generate_report()
    html = generate_html(md)

    # Save to file
    reports_dir = Path(__file__).parent.parent / 'reports'
    reports_dir.mkdir(exist_ok=True)
    md_path = reports_dir / f"{TODAY_STR}.md"
    html_path = reports_dir / f"{TODAY_STR}.html"
    latest_path = reports_dir / 'latest.html'

    md_path.write_text(md, encoding='utf-8')
    html_path.write_text(html, encoding='utf-8')
    latest_path.write_text(html, encoding='utf-8')

    # Save to DB
    title = f"哈中农业贸易日报 {TODAY_CN}"
    db.save_report(TODAY_STR, title, md, html)

    print(f"✓ Report saved: {md_path.name} ({md_path.stat().st_size:,} bytes)")
    print(f"✓ HTML: {html_path.name}")
    print(f"✓ DB: reports table updated")

if __name__ == '__main__':
    main()
