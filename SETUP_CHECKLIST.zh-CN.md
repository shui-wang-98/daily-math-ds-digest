# 本地 Codex 每日摘要设置清单

## 架构

```text
本地 Codex 定时任务
    -> prepare_run 获取论文元数据
    -> Codex 阅读标题和摘要，写入 analysis_run.json
    -> finalize_run 验证并生成 HTML / PDF / Markdown / JSON
    -> 本地测试和人工式逐项检查
    -> git commit 和 push
    -> GitHub Actions 发布已提交的 site/ 并发送 Issue 通知
```

**不需要 OpenAI API key、OpenAI Python SDK、OpenAI API 计费或其他付费 AI API。** Python 脚本不调用模型。分析由桌面应用中的 Codex 完成，使用已有 ChatGPT 登录和相应账户使用额度；这不表示 Codex 订阅无限或免费。

## 本地准备

- [ ] 安装 Python 3.12 或更新版本，保留本地 Git 仓库。
- [ ] 在仓库根目录运行 `python -m venv .venv`。
- [ ] PowerShell 运行 `.\.venv\Scripts\Activate.ps1`。如果激活受限，直接使用虚拟环境里的可执行文件。
- [ ] 运行 `python -m pip install -r requirements.txt`。
- [ ] 运行 `pytest -q`。测试只使用本地 RSS fixture，不访问 arXiv。
- [ ] 阅读并保留 `config.yaml` 中的研究画像，以及现有英文报告模板。
- [ ] 阅读 [DAILY_AUTOMATION.md](DAILY_AUTOMATION.md) 和 [README.md](README.md)。
- [ ] 用已有 Git 登录配置验证今后的推送权限；不要为本项目新建 AI 或邮件密钥。

## 离线演示

以下命令全部在仓库根目录执行。输出位于被 Git 忽略的 `tmp/offline-demo/`，不会污染真实 `data/state.json` 或发布目录。测试论文是虚构样本。

```powershell
python -m src.prepare_run --local-feed tests/fixtures/math_ds.xml --report-date 2026-09-04 --data-dir tmp/offline-demo/data
Copy-Item tests/fixtures/analysis_run.json tmp/offline-demo/data/analysis_run.json
python -m src.finalize_run --analysis tmp/offline-demo/data/analysis_run.json --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
python -m src.notify --check-only --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
python -m src.finalize_run --analysis tmp/offline-demo/data/analysis_run.json --data-dir tmp/offline-demo/data --site-dir tmp/offline-demo/site
```

- [ ] 打开演示 HTML、PDF、Markdown、JSON 和主页，确认三种优先级与链接。
- [ ] LOW PRIORITY 仅显示标题、作者、arXiv 编号。
- [ ] HIGH PRIORITY 和 RELATED 保留完整英文摘要分析和原始摘要。
- [ ] PDF 延续 ReportLab 排版，将 LaTeX 转为可读文本；复杂公式必须逐项检查，不能假定等同于 TeX 排版。
- [ ] 最后一次重复 finalization 保持文件内容和状态不变。

如果该演示已经执行过，只重跑 finalizer，或在准备和完成命令中统一换用新的空演示目录。重复 preparation 会按已有状态过滤已完成的测试论文。

## 将来的真实运行

```powershell
python -m src.prepare_run
# Codex 按 DAILY_AUTOMATION.md 写入 data/analysis_run.json
python -m src.finalize_run --analysis data/analysis_run.json
pytest -q
python -m src.notify --check-only
```

准备阶段包括 `new`、`cross`、`replace-cross`，排除纯 `replace`，不会标记已读。默认报告日期是 Europe/Warsaw 的本地运行日期。分析必须逐一覆盖 pending 中的全部论文，日期一致，不得有重复、缺失或额外 ID。以 [Pydantic 模型](src/models.py) 和 [JSON Schema](schemas/analysis_run.schema.json) 为准。

所有输出和主页成功生成后才更新状态。失败时保留 pending 和 analysis，修复后重跑 finalizer；不要先准备别的运行。每次只运行一条完整流程。单个文件使用原子替换，多个文件之间不是一个数据库事务；磁盘写入中途失败时，状态不会提前更新，重跑可恢复。

无新论文时仍写入当前日期、简短英文 overview 和空 `papers` 列表，生成 no-new-papers 报告。同日重跑不会抹去当天已有报告；同日新增论文会合并到已有报告。

## GitHub 设置

- [ ] 用户审阅本次修改后自行提交、推送；本次迁移不执行这些操作。
- [ ] **Settings > Pages > Build and deployment > Source** 选择 **GitHub Actions**。
- [ ] **Settings > General > Features > Issues** 已启用。
- [ ] 允许工作流发布 Pages 和写入 Issues；无需添加自定义 Secret。
- [ ] 将来推送 `main` 中已生成的 `data/reports/**` 或 `site/**` 后，检查 **Publish math.DS digest** 工作流。
- [ ] 也可在 `main` 手动执行 `workflow_dispatch`；没有 GitHub cron 定时器。
- [ ] 工作流只验证已提交产物、发布 Pages、发 Issue 通知，不重新生成或修改摘要。
- [ ] 打开固定 **Daily math.DS Digest notifications** Issue 并点击 **Subscribe**。
- [ ] 如需 GitHub 管理的邮件或手机通知，在个人 GitHub 通知设置中选择。
- [ ] 确认通知中的最新 HTML 和 PDF 链接可用。最新报告来自已提交 JSON/PDF，不依赖本地 `run_metadata.json`。

Issue 通知默认开启；直接邮件默认关闭，SMTP/Resend 发件实现已移除，无需邮件账号或密钥。GitHub Actions 自动提供作业令牌。首次尚无报告时只发布初始主页，不发送通知；最新报告文件不全时停止发布。

## 以后再设置桌面定时任务

**计划：周一至周五 11:00，Europe/Warsaw，按当地夏令时变化。定时任务本身稍后在桌面应用中配置，本次不创建。**

- [ ] 选择本地仓库，并让任务严格执行 `DAILY_AUTOMATION.md`。
- [ ] 到运行时，电脑必须开机且保持唤醒，连接网络，ChatGPT/Codex 桌面应用必须运行。
- [ ] 项目目录保持可用，并允许任务在该目录运行所需的命令。
- [ ] 只有验证、测试以及 HTML/Markdown/PDF/JSON 检查全部成功后，将来的任务才可提交并推送生成文件。
- [ ] 不把 fixture 演示报告、pending、analysis、虚拟环境或 `tmp/` 提交为真实报告。

桌面本地任务的运行条件见 [OpenAI 官方定时任务文档](https://learn.chatgpt.com/docs/automations?surface=app)。
