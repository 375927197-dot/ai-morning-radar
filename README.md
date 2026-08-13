# AI早盘雷达

面向 A 股 AI 科技交易前准备的自动晨报：汇总隔夜美股、韩国早盘、宏观日历与 AI 新闻，通过 QQ 邮箱发送完整晨报，并生成 Markdown、HTML、JSON 归档。

## 快速开始

```powershell
python -m pip install -e .
python -m ai_morning_radar run --fixture --dry-run
```

报告会写入 `reports/YYYY-MM-DD/`。离线夹具不访问网络、不调用 OpenAI，也不发送邮件。

真实数据干跑：

```powershell
python -m ai_morning_radar run --dry-run
```

正式运行前配置环境变量：

- `OPENAI_API_KEY`：OpenAI API 密钥；缺失时自动使用规则版分析。
- `OPENAI_MODEL`：可选，默认 `gpt-5.6-luna`。
- `QQ_EMAIL_ADDRESS`：用于发信的 QQ 邮箱，例如 `123456@qq.com`。
- `QQ_EMAIL_AUTH_CODE`：QQ 邮箱 SMTP 授权码，不是 QQ 密码。
- `EMAIL_TO`：可选，收件地址；不配置时默认发送给 `QQ_EMAIL_ADDRESS` 自己。多个地址用英文逗号分隔。

正式运行：

```powershell
python -m ai_morning_radar run
```

工作流会在工作日北京时间 08:32 启动，08:50 后补采韩国早盘，生成并提交报告，目标在 09:10 左右把邮件发送到收件箱。首次使用时应将仓库设为私有，并在 Actions 中授予工作流“读写仓库内容”权限。

## 配置 QQ 邮箱推送

1. 登录 QQ 邮箱，在邮箱设置中开启 SMTP 服务并生成授权码。授权码只显示一次，请妥善保存，不要填写 QQ 密码。
2. 打开本项目的 GitHub 仓库，依次进入“设置”→“机密和变量”→“操作”。
3. 新建仓库机密 `QQ_EMAIL_ADDRESS`，值填写完整 QQ 邮箱地址。
4. 新建仓库机密 `QQ_EMAIL_AUTH_CODE`，值填写刚生成的 SMTP 授权码。
5. 如果要发往不同邮箱，在“变量”页新建 `EMAIL_TO`；发送给自己则不用设置。
6. 打开“操作”页，手动运行一次 `AI早盘雷达` 工作流，确认能收到测试晨报。

邮件会同时包含可直接阅读的 HTML 正文和同名 HTML 附件。发送失败会自动重试 3 次，并尝试发送简短故障通知。

## 数据与风险说明

- yfinance 免费行情可能延迟、缺失或更改代码，不是交易所级实时行情。
- AI 只解释确定性评分，不得修改行情和评分；AI 不可用时自动降级为规则模板。
- 本工具仅用于信息整理与风险观察，不构成投资建议，也不执行交易。
