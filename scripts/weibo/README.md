# 微博博主帖子整理工具

抓取指定微博博主在某个时间范围内的帖子，生成本地化报告（Markdown + HTML，含配图）。

## 依赖

```bash
pip install playwright
python -m playwright install chromium   # 或使用本机已装的 Chrome（channel="chrome"）
```

## 使用流程

### 1. 扫码登录（首次 / 登录态失效时）

```bash
python scripts/weibo/wb_login.py
```

会打开一个**独立的** Chrome 窗口，用手机微博 App 扫码即可。
登录态保存在 `~/weibo_profile`（可用环境变量 `WEIBO_PROFILE` 指定），
后续抓取自动复用，不会影响你日常使用的 Chrome。

> ⚠️ 该目录包含登录 Cookie，**切勿提交到 git**（仓库 `.gitignore` 已排除）。

### 2. 抓取并生成报告

```bash
python scripts/weibo/weibo_report.py "博主昵称" [起始日期 YYYY-MM-DD]
```

示例：

```bash
python scripts/weibo/weibo_report.py "王虎的舰桥" 2026-07-21   # 指定起始日期
python scripts/weibo/weibo_report.py "王虎的舰桥"              # 默认最近 60 天
python scripts/weibo/weibo_report.py 6545577536               # 也可直接传 uid
```

输出到 `reports/weibo/<博主名>_微博报告/`：

```
<博主名>_微博报告/
├── <博主名>_<起>-<止>.md      整理报告
├── <博主名>_<起>-<止>.html    整理报告（推荐阅读）
└── images/                    配图（本地化）
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEIBO_PROFILE` | `~/weibo_profile` | 登录态目录（含凭证） |
| `WEIBO_OUTDIR`  | 仓库 `reports/weibo/` | 报告输出目录 |

## 实现要点

- **必须登录**：微博公开接口匿名访问返回 `HTTP 432` 并跳转访客页，故依赖扫码登录态。
- **接口**：`m.weibo.cn` 的 `container/getIndex`（时间线）、`statuses/extend`（长文全文）。
- **置顶帖**：首页首条若远早于次条，判定为置顶，不参与时间边界判断。
- **图片**：微博图床校验 Referer，本地 HTML 无法加载，故将图片下载到本地 `images/`（`bmiddle` 尺寸）。
- **限速**：翻页间隔 2.5s、长文 1.2s，避免触发风控。

## 声明

仅供个人阅读整理使用，请勿用于公开传播或商业用途。
