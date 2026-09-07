# 部署检查清单

## 必需

- [ ] 在 GitHub 创建 Public repository，例如 `daily-math-ds-digest`
- [ ] 上传本 ZIP 中的全部文件，包括 `.github/workflows/daily.yml`
- [ ] 在 `Settings → Secrets and variables → Actions → Secrets` 添加 `OPENAI_API_KEY`
- [ ] 在 `Settings → Pages → Build and deployment → Source` 选择 `GitHub Actions`
- [ ] 确认 `Settings → General → Features → Issues` 已启用
- [ ] 在 `Actions → Daily math.DS digest` 手动执行第一次 workflow
- [ ] 打开自动创建的 `Daily math.DS Digest notifications` Issue 并点击 `Subscribe`
- [ ] 在 GitHub 个人通知设置中开启 Email 或移动端通知

## 可选：PDF 邮件附件

### Resend

- [ ] `RESEND_API_KEY`
- [ ] `EMAIL_TO`
- [ ] `EMAIL_FROM`（必须属于已验证域名）

### 或 SMTP

- [ ] `SMTP_HOST`
- [ ] `SMTP_PORT`
- [ ] `SMTP_SECURITY`（`starttls` 或 `ssl`）
- [ ] `SMTP_USERNAME`
- [ ] `SMTP_PASSWORD`
- [ ] `EMAIL_TO`
- [ ] `EMAIL_FROM`

## 第一次成功后的检查

- [ ] GitHub Pages 主页能够打开
- [ ] 当天 HTML 报告能够打开
- [ ] 当天 PDF 能够下载
- [ ] `data/reports/YYYY-MM-DD.json` 已提交
- [ ] 固定通知 Issue 中出现当天评论
- [ ] 若配置了邮件，收到 PDF 附件

默认运行时间：**周一至周五 11:00，Europe/Warsaw**。
