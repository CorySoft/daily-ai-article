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
2. 在仓库 `Settings → Secrets → Actions` 添加：
   - 生成文章：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`
   - 发布到微信：`WX_SERVER`、`WX_SHARED_SECRET`、`WX_APPID`、`WX_APPSECRET`
   - 可选：`ARTICLE_AUTHOR`、`ARTICLE_DIGEST`（作者、摘要）

### 申请 SiliconFlow Key
1. 打开 https://cloud.siliconflow.cn 注册登录（国内直连）
2. 进入「API 密钥」页面 → 创建 API 密钥 → 复制保存
3. 在「模型广场」挑一个模型，复制其完整模型名作为 `LLM_MODEL`
   - 免费/低价推荐：`deepseek-ai/DeepSeek-V3`（性价比高）、`Qwen/Qwen3-8B`（免费）
4. 用生成的 key 填 `LLM_API_KEY` 即可

### 微信发布配置
文章会通过你的 `wechat-publisher` 中转服务存到草稿箱，需要在 Actions 加 secret：
- `WX_SERVER`：你的中转服务地址，如 `https://your-host`
- `WX_SHARED_SECRET`：与 wechat-publisher `config.php` 的 `shared_secret` 一致
- `WX_APPID` / `WX_APPSECRET`：公众号凭证（client 脚本会加密传输，服务器不落盘）

> 草稿箱接口不要求公众号认证，未认证账号也能用。要正式群发/发布需认证。
> IP 白名单加你的 PHP 服务器 IP 即可（微信请求由你的固定服务器发出，GitHub 动态 IP 不影响）。

### 换其他服务（可选）
均为 OpenAI 兼容接口，改 `LLM_BASE_URL` + `LLM_MODEL` 即可：
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
