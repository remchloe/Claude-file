# Claude-file

由 Claude 生成的文件和聊天记录存储仓库。

## 目录结构

```
Claude-file/
├── chat-records/              # 聊天记录
│   ├── summaries/             # 对话摘要
│   └── full-logs/             # 完整对话
├── generated-files/           # 生成的文件
│   ├── scripts/               # 脚本代码（如 ETF 数据抓取）
│   ├── data/                  # 数据文件（如 CSV）
│   ├── documents/             # 其他文档
│   └── configs/               # 配置文件
├── reports/                   # 分析报告
│   ├── ETF周报/日报...md        # ETF 分析报告
│   └── weibo/                 # 微博博主整理报告
│       └── <博主名>_微博报告/    # .md/.html + images/(配图不入库)
├── scripts/weibo/             # 微博抓取工具（详见其 README.md）
│   ├── wb_login.py            #   扫码登录（一次性）
│   └── weibo_report.py        #   抓取 + 生成报告
├── data/weibo/                # 微博结构化数据（JSON）
├── references/                # 参考文档（三重SKILL体系）
│   ├── etf-analysis_SKILL.md    # [理论] ETF分类/指标/策略/代码模板
│   ├── etf-operation_SKILL.md   # [实战] ⭐盘前流程/偏差记录/持续改进
│   │                             # 每次操作前必读，每次偏差后更新
│   └── etf-system_OVERVIEW.md   # [概览] ⭐⭐ 新会话从这里开始！
│                                 # 包含完整架构/流程/路线图/经验教训
├── assets/                    # 其他资源
├── .gitignore
└── README.md
```

## 使用说明

| 目录 | 用途 |
|------|------|
| `chat-records/summaries` | 保存与 Claude 对话的关键摘要 |
| `chat-records/full-logs` | 保存完整对话记录 |
| `generated-files/scripts` | 存放生成的脚本代码 |
| `generated-files/data` | 存放数据文件（CSV 等） |
| `generated-files/documents` | 存放其他文档 |
| `generated-files/configs` | 存放配置文件 |
| `reports/` | 存放分析报告（ETF 周报/日报等） |
| `reports/weibo/` | 微博博主整理报告（HTML/MD，配图见下） |
| `scripts/weibo/` | 微博抓取工具，用法见 `scripts/weibo/README.md` |
| `data/weibo/` | 微博结构化数据（JSON，可直接检索） |
| `references/` | 参考文档、SKILL 文件（详见上方目录结构说明） |
| `assets/` | 存放图片等资源文件 |

## 微博整理模块

抓取指定博主某时间段内的帖子并生成本地化报告。

> 运行方式见 `scripts/weibo/README.md`。首次需扫码登录（`wb_login.py`）。

- **登录态**：保存在 `~/weibo_profile`，含 Cookie，**禁止提交**（`.gitignore` 已排除）。
- **配图**：报告 HTML/MD 已入库；`images/` 目录（数十 MB 二进制）默认**不入库**，
  可从 `data/weibo/*.json` 中的 `images` 字段用脚本重新下载，或在本地保留即可离线查看。

## 同步命令

```bash
cd E:\claudeCode
git add -A
git commit -m "说明本次修改内容"
git push
```
