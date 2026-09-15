# 本地 Codex 每日摘要部署清单

架构：GitHub Actions 下载并验证官方 math.DS RSS，归档原始 XML/manifest
→ 本地 Git 同步 inbox → Codex 离线准备和英文分析 → HTML/JSON
→ 验证后提交推送 → 现有 Pages 发布和日报 Issue 通知。

研究画像、三级分类、数学可靠性规则、原始 abstract 和 HTML 设计保持不变。
不使用模型 API、AI SDK、付费 AI 服务或新密钥，不生成新的 PDF/Markdown，
不改写历史下载文件。详细实现与日期语义见 [README.md](README.md)。

## 部署前

- [ ] 阅读 AGENTS.md、DAILY_AUTOMATION.md 和 VALIDATION.md 的真实验证记录。
- [x] 2026-09-15 获得正式部署批准，修复已合并 main 并推送。
- [x] 经批准更新并恢复现有本地任务，保持原任务身份和工作日 12:00 时间；未新建任务。
- [ ] 不改变全局 Codex 配置，不扩大成整个 Git 或整台电脑的权限。

## 云端抓取

- [ ] capture-rss.yml：工作日 11:15 Europe/Warsaw，自动跟随夏令时，可手动触发。
- [ ] GitHub 官方已支持 cron 旁的 timezone；但定时任务可能延迟。
- [ ] 仅用内置 GITHUB_TOKEN 的 contents:write 提交本次 XML/manifest，不添加密钥。
- [ ] 输入按公告日期/SHA256 追加且可追溯，不能覆盖已处理输入。
- [ ] 下载失败、XML/分类/日期/校验失败明确停止，不伪装成空日报。
- [ ] 抓取不改 state、不分析、不部署、不发通知。

公告日期在抓取时必须是 Europe/Warsaw 最近的工作日；周末取周五。
更新延迟和特殊节假日需要等待真实输入，不猜测节日日历。

## 本地正式路径

- [ ] 使用仓库 .venv 中的 Python；无需依赖激活或 PATH。
- [ ] 使用已有 Git 认证执行 git pull --ff-only origin main。
- [ ] python -m src.prepare_run 只读本地 inbox，无 HTTP 或联网回退。
- [ ] 退出码 0 表示准备成功；2 表示 INPUT NOT READY；3 表示当前输入已全部完成。
- [ ] PowerShell 命令调用中紧接准备命令执行 exit $LASTEXITCODE，保留原始退出码；完整调用见 DAILY_AUTOMATION.md。
- [ ] 先恢复未完成 pending/analysis，再按公告日期处理积压，不能跳过未开机时留下的输入。
- [ ] 报告日期来自 feed；抓取、公告、准备、生成时间分别保存，不把旧公告改成今天。
- [ ] 每篇论文按原 schema 分析，不能将 fixture 用于正式数据或恢复。
- [ ] 所有 HTML/JSON 和首页成功生成后，才同时更新 seen 和 processed_inputs。
- [ ] 失败保留分析并重试；同日空结果不得覆盖非空日报。
- [ ] 外部链接仅做本地 URL/arXiv ID 对应检查，不访问 arXiv。
- [ ] 完整测试和显示检查通过后，使用固定说明 Add daily math.DS digest 提交。
- [ ] 日常 Git 命令遵循 DAILY_AUTOMATION.md，与现有 .codex 规则一致，不扩大规则。

测试只使用忽略的临时目录，显式指定 data/site/inbox 路径，不污染正式 state、
报告、inbox 或网站。

## 发布及无人值守验收

- [ ] Pages 来源选择 GitHub Actions，Issues 启用。
- [ ] daily.yml 只发布真实报告/site；inbox-only 提交不通知“日报完成”。
- [x] 本地任务时间保持工作日 12:00 Europe/Warsaw，已使用当前离线 inbox 指令恢复。
- [x] 当前会话实测：真实云端输入 → Git 同步 → 离线分析 → HTML/JSON → Codex 执行提交推送 → Pages 与通知。
- [x] 已读取 2026-09-15 16:01 Europe/Warsaw 的真实任务日志：拉取成功，当前输入已完成，未改写或重复发布日报。
- [ ] 仍须由有新输入的真实任务验证离线分析、生成和自动提交推送；本次按规则跳过这些步骤。
- [ ] 工作日 12:00 的实际调度准时性仍待观察；此次运行时间不能作为准时性的证据。

可复用诊断证据、CI 链接、视觉检查与未验收项目统一记录在 VALIDATION.md。
退出码 1/3 差异已实测定位为 PowerShell 包装行为，已修正仓库调用指令，
无需修改 Python 或任务配置。无需再人为运行一次已完成的输入；下一次有真实新输入
的任务日志才能补齐剩余验收，不能以普通会话的手动执行代替。
