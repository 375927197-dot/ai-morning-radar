# AI早盘雷达

面向 A 股 AI 科技交易前准备的自动晨报：汇总隔夜美股、韩国早盘、宏观日历与 AI 新闻，生成企业微信摘要以及 Markdown、HTML、JSON 完整报告。

## 快速开始

```powershell
python -m pip install -e .
python -m ai_morning_radar run --fixture --dry-run
```

报告会写入 `reports/YYYY-MM-DD/`。离线夹具不访问网络、不调用 OpenAI，也不推送企业微信。

真实数据干跑：

```powershell
python -m ai_morning_radar run --dry-run
```

正式运行前配置环境变量：

- `OPENAI_API_KEY`：OpenAI API 密钥；缺失时自动使用规则版分析。
- `OPENAI_MODEL`：可选，默认 `gpt-5.6-luna`。
- `WECOM_WEBHOOK_URL`：企业微信群机器人 Webhook；缺失时跳过推送。

正式运行：

```powershell
python -m ai_morning_radar run
```

GitHub Actions 所需 Secrets 同上。工作流会在工作日北京时间 08:32 启动，08:50 后补采韩国早盘，生成并提交报告。首次使用时应将仓库设为私有，并在 Actions 中授予工作流“读写仓库内容”权限。

## 数据与风险说明

- yfinance 免费行情可能延迟、缺失或更改代码，不是交易所级实时行情。
- AI 只解释确定性评分，不得修改行情和评分；AI 不可用时自动降级为规则模板。
- 本工具仅用于信息整理与风险观察，不构成投资建议，也不执行交易。

