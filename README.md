# 每日 AI 公众号文章（S1-S7 全流程）

定时全网检索 → AI 策划 → AI 原创撰写 → 自检验收 → 存入公众号草稿箱（不群发）。

## 流程
```
GitHub Actions cron(每天 8:00)
  S1 search.py    调用 Brave Search 全网检索 → output/collected.json
  S2 plan.py      调用 LLM 内部分析策划 → output/plan.json
  S3 write.py     调用 LLM 原创撰写(1800~3000字) → output/YYYY-MM-DD.md + article.json
  S7 report.py    自检验收 → output/report.json
  S6 publish.js   调用 wechat-publisher 中转 → 存草稿箱
  → 你在公众号后台手动点发布
```

## 配置
在仓库 `Settings → Secrets and variables → Actions` 添加：

### 🔒 Secrets（保密，加密存储）
- `LLM_API_KEY`：火山方舟 API Key
- `SEARCH_API_KEY`：Brave Search API Key
- `WX_SERVER`：wechat-publisher 中转地址（如 `https://your-host`）
- `WX_SHARED_SECRET`：与 config.php 的 shared_secret 一致
- `WX_APPID`：公众号 AppID
- `WX_APPSECRET`：公众号 AppSecret

### 🔓 Variables（公开配置，明文可见）
- `LLM_BASE_URL`：`https://ark.cn-beijing.volces.com/api/v3`
- `LLM_MODEL`：火山方舟接入点 ID（如 `ep-xxxxxxxx`）
- `SEARCH_TOPICS`：检索主题，用 `|` 分隔，如 `人工智能 最新进展|大模型 发布`
- `ARTICLE_AUTHOR`：作者名，如 `小编`
- `ARTICLE_DIGEST`：摘要（可空）

### 申请 Brave Search Key（S1 检索）
1. 打开 https://brave.com/search/api/ 注册登录
2. 创建 API Key（免费 2000 次/月）
3. 填 `SEARCH_API_KEY`（Secret）

### 申请火山方舟 Key（LLM）
1. 打开 https://console.volcengine.com/ark 开通模型
2. 创建「接入点」（推理接入点），复制接入点 ID 填 `LLM_MODEL`（Variable）
3. 创建 API Key 填 `LLM_API_KEY`（Secret）

### 微信发布配置
文章通过 `wechat-publisher` 中转服务存草稿箱，`WX_*` 四个值填 **Secrets**。

> 草稿箱接口不要求公众号认证。IP 白名单加你的 PHP 服务器 IP（请求由你的固定服务器发出，GitHub 动态 IP 不影响）。

## 运行
- 每天 8:00 自动运行
- 也可在 Actions 页手动点 `Run workflow` 立即生成

## 自定义
- 检索主题：改 Variable `SEARCH_TOPICS`
- 写作要求：改 `scripts/write.py` 的 `WRITE_PROMPT`
- 策划要求：改 `scripts/plan.py` 的 `PLAN_PROMPT`

## 当前阶段
文字链路（S1/S2/S3/S6/S7）已实现。**配图（S3 插图 / S4 封面）待后续接入 agnes.ai 生图**，届时新增生图与图片上传步骤。
