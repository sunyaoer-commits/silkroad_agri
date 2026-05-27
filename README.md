# 丝路农贸 (SilkRoad Agri) — 部署说明

## 系统结构

```
silkroad-data/
├── index.html              ← 首页（GitHub Pages入口）
├── platform.html           ← 完整平台前端（已附在zip中）
├── data/
│   └── market_data.json    ← 每日自动更新的数据文件（前端读取）
├── reports/
│   ├── YYYY-MM-DD.md       ← 每日中文报告（Markdown）
│   ├── YYYY-MM-DD.html     ← 每日中文报告（HTML，可发布）
│   └── latest.html         ← 最新报告（网页平台直接读取）
├── db/
│   └── silkroad.db         ← SQLite数据库（18个月历史数据）
├── scripts/
│   ├── db.py               ← 数据库管理器
│   ├── fetch.py            ← 数据抓取主脚本
│   └── report.py           ← 每日报告生成器
└── .github/
    └── workflows/
        └── pipeline.yml    ← GitHub Actions自动化配置
```

---

## 10分钟部署步骤

### 第一步：Fork 到你的 GitHub 账号

1. 登录 [github.com](https://github.com)
2. 新建一个仓库，命名为 `silkroad-agri`（或任意名字）
3. 将这个文件夹的所有文件上传到仓库

### 第二步：开启 GitHub Pages

1. 进入仓库 → **Settings** → **Pages**
2. Source 选择 `main` 分支，`/ (root)` 目录
3. 点击 **Save**
4. 等待2分钟，访问 `https://你的用户名.github.io/silkroad-agri/`

### 第三步：添加 UN Comtrade API 密钥（免费）

1. 访问 [comtradeplus.un.org](https://comtradeplus.un.org/) 注册免费账号
2. 在账户设置中获取 API Key
3. 在 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**
4. 添加新的 Secret：名称 `COMTRADE_KEY`，值填入你的API Key

### 第四步：验证 GitHub Actions 是否运行

1. 进入仓库 → **Actions** 标签
2. 找到 "Daily Data Pipeline"
3. 点击 **Run workflow** 手动触发一次
4. 等待2分钟，刷新仓库，检查 `data/market_data.json` 是否更新

**完成！之后每天自动运行，零维护。**

---

## 数据来源

| 来源 | 数据内容 | 更新频率 | 费用 |
|------|---------|---------|------|
| UN Comtrade | 哈中双边贸易量/额（HS 1204/1003/1206/1512） | 月度（延迟45天） | 免费（需注册） |
| chinadata.live | 中国GACC官方进出口统计 | 月度 | 完全免费 |
| frankfurter.app | USD/KZT, USD/CNY 汇率 | 每日 | 完全免费 |
| World Bank | 全球大宗商品价格指数 | 月度 | 完全免费 |
| USDA FAS GAIN | 哈萨克斯坦农业报告 | 月度 | 完全免费 |
| Grain Union KZ | 市场新闻动态 | 每日抓取 | 免费（公开网页） |
| 手动更新 | 现货价格、铁路运费 | 每周（你手动更新） | — |

---

## 手动更新现货价格

在 `scripts/fetch.py` 文件中找到 `MANUAL_PRICES` 字典，每周更新一次：

```python
MANUAL_PRICES = {
    'flaxseed': [
        ('ewx_kostanay', 488, None, 240000, 'Grain Union KZ W21/2026'),  # ← 改这里
        ('fca_kz', 512, None, None, 'Grain Union KZ W21/2026'),
        ('cf_tianjin', 571, None, None, 'APK-Inform W21/2026'),
        ...
    ],
```

数据来源（每周查看）：
- 哈萨克粮食联盟周报：[grainunion.kz](https://grainunion.kz)
- APK-Inform：[apk-inform.com](https://apk-inform.com)
- 宁夏亚麻籽价格：可问当地贸易商，或查 [导油网 oilcn.com](http://www.oilcn.com)

---

## 公众号集成（后续步骤）

每日报告生成在 `reports/YYYY-MM-DD.md`，可以：

1. **手动发布**：每天早上复制 `latest.html` 内容，粘贴到公众号编辑器
2. **半自动**：使用微信公众号API（需认证公众号）+ GitHub Actions webhook
3. **工具推荐**：[Doocs-MD](https://doocs.github.io/md/) —— 将Markdown一键转换为微信公众号格式

---

## 成本

| 项目 | 成本 |
|------|------|
| GitHub Pages | 免费 |
| GitHub Actions | 免费（2000分钟/月，本系统约用120分钟/月） |
| 域名（可选）| ~¥60/年（阿里云） |
| 所有API | 免费 |
| **总计** | **$0 — ¥60/年（如需自定义域名）** |

---

## 技术栈

- **数据层**：Python 3.11 + SQLite（`db/silkroad.db`）
- **自动化**：GitHub Actions (YAML)
- **前端**：纯HTML/CSS/JS（无框架，无CDN依赖，可完全离线运行）
- **图表**：原生Canvas API（无需任何图表库）
- **部署**：GitHub Pages

---

*如有问题，联系：contact@silkroadagri.com*
