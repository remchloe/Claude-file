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
├── reports/                   # 分析报告（ETF周报/日报）
├── references/                # 参考文档（双SKILL体系）
│   ├── etf-analysis_SKILL.md    # [理论] ETF分类/指标/策略/代码模板
│   └── etf-operation_SKILL.md   # [实战] ⭐盘前流程/偏差记录/持续改进
│                                 # 每次操作前必读，每次偏差后更新
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
| `reports/` | 存放分析报告（周报等） |
| `references/` | 参考文档、SKILL 文件（详见上方目录结构说明） |
| `assets/` | 存放图片等资源文件 |

## 同步命令

```bash
cd C:\Users\admin\Claude-file
git add -A
git commit -m "说明本次修改内容"
git push
```
