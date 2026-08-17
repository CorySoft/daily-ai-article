# 每日 AI 公众号文章

定时收集信息 → AI 撰写 → 生成 Markdown 文章（你手动复制到公众号发布）

## 流程
```
GitHub Actions cron(每天 8:00)
  → scripts/collect.py 抓取信息
  → scripts/write.py 调 LLM 生成文章(输出 .md + article.json)
  → 调用你的 wechat-publisher 中转服务 → 存草稿箱
  → 你在公众号后台手动点发布
```

## 配置
1. 把项目推到 **public 仓库**（Actions 不限量）
2. 在仓库 `Settings → Secrets and variables → Actions` 添加：

### 🔒 Secrets（保密，加密存储，显示为 ***）
- `LLM_API_KEY`：硅基流动 API Key
- `WX_SERVER`：wechat-publisher 中转地址（如 `https://your-host`）
- `WX_SHARED_SECRET`：与 config.php 的 shared_secret 一致
- `WX_APPID`：公众号 AppID
- `WX_APPSECRET`：公众号 AppSecret

### 🔓 Variables（公开配置，明文可见）
- `LLM_BASE_URL`：`https://api.siliconflow.cn/v1`
- `LLM_MODEL`：`THUDM/GLM-4-9B-Chat`（免费中文写作）
- `ARTICLE_AUTHOR`：作者名，如 `小编`
- `ARTICLE_DIGEST`：摘要（可空）

### 申请 SiliconFlow Key
1. 打开 https://cloud.siliconflow.cn 注册登录（国内直连）
2. 进入「API 密钥」页面 → 创建 API 密钥 → 复制保存
3. 用生成的 key 填 `LLM_API_KEY`（Secret）
4. 在「模型广场」找免费模型 `THUDM/GLM-4-9B-Chat` 或 `Qwen/Qwen2.5-7B-Instruct`，填 `LLM_MODEL`（Variable）

### 微信发布配置
文章会通过你的 `wechat-publisher` 中转服务存到草稿箱，其中 `WX_*` 四个值填到 **Secrets**。

> 草稿箱接口不要求公众号认证，未认证账号也能用。要正式群发/发布需认证。
> IP 白名单加你的 PHP 服务器 IP 即可（微信请求由你的固定服务器发出，GitHub 动态 IP 不影响）。

### 换其他服务（可选）
均为 OpenAI 兼容接口，改 `LLM_BASE_URL` + `LLM_MODEL` 两个 **Variables** 即可：
- DeepSeek：`https://api.deepseek.com/v1`
- Groq：`https://api.groq.com/openai/v1`
- Google Gemini：官方 API
- GitHub Models：需 Copilot 订阅

## 运行
- 每天 8:00 自动运行
- 也可在 Actions 页手动点 `Run workflow` 立即生成

## 自定义主题
编辑 `scripts/collect.py` 的 `collect_news()`，改为你要的信息源（天气、行情、行业资讯等），并同步改 `build_prompt()` 的撰写要求。

## 公众号发布
未认证的个人订阅号无发布 API，文章生成后请在 `output/` 找到当日 `.md`，复制到公众号后台手动发布。
