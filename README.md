# Daily math.DS Digest

一个可直接部署到 GitHub 的个人化 arXiv `math.DS` 日报系统。

它在 **Europe/Warsaw 时区，每周一至周五 11:00** 自动运行，读取 arXiv 官方 `math.DS` RSS feed，只保留：

- `new`：新投稿；
- `cross`：新 cross-list 到 `math.DS` 的论文；
- `replace-cross`：在本次更新中同时发生 replacement/cross-list 的论文；

并排除单纯的 `replace` 版本更新。

AI 只使用论文的 **title + abstract + categories + announce type**，根据预设研究兴趣分为：

1. **HIGH PRIORITY**：完整英文研究摘要；
2. **RELATED / POSSIBLY INTERESTING**：完整英文研究摘要，并解释相关性；
3. **LOW PRIORITY**：只显示题目和作者；题目链接到 arXiv。

每日自动生成并永久归档：

- GitHub Pages HTML 报告；
- 可下载 PDF；
- Markdown；
- JSON；
- GitHub Issue 通知；
- 可选的 PDF 邮件附件（Resend 或任意 SMTP 邮箱）。

---

## 1. 你需要准备什么

### 必需

1. 一个 GitHub 账户；
2. 一个新的 GitHub repository，建议命名为 `daily-math-ds-digest`；
3. 一个 OpenAI API key，并确保 API 账户可以正常计费。

**不要把 API key、邮箱密码或 GitHub 密码发给任何人，也不要写进代码。** 它们只应填入 GitHub Actions Secrets。

### 可选：直接收到带 PDF 附件的邮件

系统默认会创建一个固定 GitHub Issue，并在每次生成新报告时追加一条评论。只要你订阅该 Issue 并启用 GitHub 邮件/推送通知，就不需要其他服务。

若希望每天直接收到 **PDF 邮件附件**，再准备以下二选一：

- **Resend**：API key、已验证的发件域名和收件邮箱；
- **SMTP**：邮箱服务器、端口、用户名和 app password/SMTP password。

不配置邮件不会影响网页、PDF 和 GitHub Issue 通知。

---

## 2. 最快部署步骤

### 第一步：创建仓库

在 GitHub 新建一个 **Public** repository，例如：

```text
daily-math-ds-digest
```

Public repository 是最简单的 GitHub Pages 部署方式。先不要添加模板文件也可以。

### 第二步：上传本项目

解压下载的 ZIP，把其中所有文件上传到仓库根目录。必须保留以下隐藏目录和文件：

```text
.github/workflows/daily.yml
.gitignore
```

你也可以在本机使用 Git：

```bash
git init
git add .
git commit -m "Initial daily math.DS digest"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/daily-math-ds-digest.git
git push -u origin main
```

### 第三步：添加 OpenAI API key

进入：

```text
Repository → Settings → Secrets and variables → Actions → Secrets
```

点击 **New repository secret**，添加：

```text
Name:  OPENAI_API_KEY
Value: 你的 OpenAI API key
```

代码只从环境变量读取该 key。

### 第四步：启用 GitHub Pages

进入：

```text
Repository → Settings → Pages
```

在 **Build and deployment → Source** 中选择：

```text
GitHub Actions
```

### 第五步：确认仓库允许 Issue 通知

进入：

```text
Repository → Settings → General → Features
```

确认 **Issues** 已启用。

第一次成功运行后，系统会创建：

```text
Daily math.DS Digest notifications
```

打开该 Issue，点击 **Subscribe**。同时在个人 GitHub 通知设置中开启邮件或移动端通知。以后每个新报告都会在这个 Issue 中追加链接。

### 第六步：第一次手动运行

进入：

```text
Repository → Actions → Daily math.DS digest → Run workflow
```

选择默认分支并执行。第一次运行应依次完成：

```text
Check out repository
Set up Python
Install dependencies
Run tests
Build today's report
Commit report archive
Configure / upload / deploy GitHub Pages
Send notifications
```

成功后，网站地址通常为：

```text
https://YOUR_USERNAME.github.io/daily-math-ds-digest/
```

随后系统会在每个工作日 11:00（Europe/Warsaw）自动运行。

---

## 3. 可选：通过邮件直接发送 PDF

所有值都应放在：

```text
Repository → Settings → Secrets and variables → Actions → Secrets
```

### 方案 A：Resend

添加：

```text
RESEND_API_KEY
EMAIL_TO
EMAIL_FROM
```

示例：

```text
EMAIL_TO=your-address@example.com
EMAIL_FROM=math.DS Digest <digest@your-verified-domain.example>
```

`EMAIL_FROM` 必须属于你在 Resend 中验证过的域名。系统会把当天 PDF 作为附件发送。

### 方案 B：SMTP

添加：

```text
SMTP_HOST
SMTP_PORT
SMTP_SECURITY
SMTP_USERNAME
SMTP_PASSWORD
EMAIL_TO
EMAIL_FROM
```

典型 STARTTLS 配置：

```text
SMTP_PORT=587
SMTP_SECURITY=starttls
```

典型 SSL 配置：

```text
SMTP_PORT=465
SMTP_SECURITY=ssl
```

以 Gmail 为例，通常使用：

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=你的 Google app password，而不是普通登录密码
EMAIL_TO=your-address@gmail.com
EMAIL_FROM=your-address@gmail.com
```

若同时配置 Resend 与 SMTP，系统优先使用 Resend；Resend 未配置时才使用 SMTP。

---

## 4. OpenAI 模型设置

默认模型写在 `config.yaml`：

```yaml
openai:
  model: "gpt-5.6-terra"
```

不修改代码也可以覆盖它。进入：

```text
Repository → Settings → Secrets and variables → Actions → Variables
```

添加 repository variable：

```text
Name:  OPENAI_MODEL
Value: 你希望使用的模型名称
```

不要把模型名称作为 Secret；它不是敏感信息。

---

## 5. 个性化研究兴趣

当前研究画像位于 `config.yaml` 的 `research_profile` 部分，已经针对以下方向优化：

- entropy theory；
- thermodynamic formalism；
- mean dimension / metric mean dimension；
- rate-distortion dimension；
- fractal geometry 与各类 dimension；
- topological dynamics；
- symbolic dynamics、shifts、subshifts、SFTs；
- amenable / sofic / general group actions；
- 与上述主题明确相关的 smooth、hyperbolic、ergodic、complex 或 homogeneous dynamics。

同时把缺少上述联系的 ODE/PDE、数值分岔、应用建模和控制类论文降为 Low Priority。

直接编辑：

```yaml
research_profile:
  high_priority:
    - ...
  related:
    - ...
  low_priority:
    - ...
```

AI 提示词位于：

```text
prompts/paper_analysis.txt
prompts/daily_overview.txt
```

分类规则采用偏保守策略：在 `RELATED` 与 `LOW PRIORITY` 之间无法确定时，选择 `RELATED`，以减少漏报。

---

## 6. 输出位置

每次运行会提交下列归档：

```text
data/reports/YYYY-MM-DD.json
site/reports/YYYY-MM-DD/index.html
site/reports/YYYY-MM-DD/math-DS-digest-YYYY-MM-DD.pdf
site/reports/YYYY-MM-DD/math-DS-digest-YYYY-MM-DD.md
site/reports/YYYY-MM-DD/report.json
```

主页：

```text
site/index.html
```

去重状态：

```text
data/state.json
```

去重以不带版本号的 arXiv ID 为键。例如：

```text
2609.01234v1
2609.01234v2
```

都会归一化为：

```text
2609.01234
```

因此单纯的后续版本不会被当成新论文重复总结。

---

## 7. 报告可靠性约束

AI 被要求：

- 只根据 title 和 abstract 作数学陈述；
- 不虚构 theorem、assumption、proof technique、novelty 或 comparison；
- 保留 abstract 中的条件、量词与限制；
- 区分 theorem、construction、example、conjecture、numerical evidence 和 application；
- abstract 没有说明时写 `Not specified in the abstract.`；
- Low Priority 不生成详细摘要，只显示题目和作者；
- 完整条目中始终附上原始 abstract 供核对。

如果某篇论文的 OpenAI 请求在重试后仍失败，系统不会让整份日报消失，而会使用保守的 keyword fallback，并在网页/PDF 中明确标出该条目需要核对原始 abstract。

---

## 8. 修改运行时间

工作流位于：

```text
.github/workflows/daily.yml
```

当前设置：

```yaml
schedule:
  - cron: "0 11 * * 1-5"
    timezone: "Europe/Warsaw"
```

含义是 Warsaw 时区每周一到周五 11:00。使用 IANA timezone 后，夏令时切换由 GitHub 调度器处理。

例如改为工作日 10:30：

```yaml
schedule:
  - cron: "30 10 * * 1-5"
    timezone: "Europe/Warsaw"
```

---

## 9. 本地测试

需要 Python 3.12 或相近版本：

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest -q
```

用内置 RSS fixture 和 deterministic fallback 生成本地演示报告，不会调用 OpenAI：

```bash
python -m src.main \
  --local-feed tests/fixtures/math_ds.xml \
  --mock-ai
```

真实运行：

```bash
export OPENAI_API_KEY="..."
python -m src.main
```

本地构建结果在 `site/` 中。

---

## 10. 常见问题

### Pages 部署失败

确认：

1. `Settings → Pages → Source` 已设置为 **GitHub Actions**；
2. workflow 在默认分支上；
3. `Actions` 没有被仓库禁用。

### GitHub Issue 通知报 403

确认：

1. 仓库已启用 Issues；
2. workflow 中仍保留：

```yaml
permissions:
  issues: write
```

3. 若组织策略覆盖默认权限，需要管理员允许 Actions 写入 Issues。

### 没收到 GitHub 邮件

打开固定通知 Issue，点击 **Subscribe**，并检查个人 GitHub 的 Notifications 设置。网页和 PDF 即使没有邮件也仍会正常生成。

### 邮件发送失败但 Pages 已生成

通知步骤在部署之后执行。因此，即使 SMTP/Resend 配置错误导致最后一步失败，当天网页与 PDF 通常已经成功部署。修复 Secret 后，手动重新运行 workflow 即可。

### 当天没有新论文

系统仍可生成一份简短的 no-papers 报告，并按 `notifications.send_on_no_papers` 决定是否通知。默认值为 `true`。

### 不想公开自己的研究兴趣

Public Pages 仓库中的 `config.yaml` 和报告都是公开的。若研究画像或报告内容需要保密，应使用支持私有 Pages 的 GitHub 方案，或关闭 Pages，仅使用私有仓库和邮件投递。

---

## 11. 官方参考

- arXiv RSS feeds: https://info.arxiv.org/help/rss.html
- arXiv RSS specification: https://info.arxiv.org/help/rss_specifications.html
- GitHub Actions workflow syntax: https://docs.github.com/actions/using-workflows/workflow-syntax-for-github-actions
- GitHub Pages custom workflows: https://docs.github.com/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- OpenAI model documentation: https://platform.openai.com/docs/models
- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- Resend attachments: https://resend.com/docs/dashboard/emails/attachments

