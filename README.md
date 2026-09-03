# 每日 AI 公众号文章

定时全网检索 → AI 策划 → AI 原创撰写 → 配图 → 自检验收 → 存入公众号草稿箱（不群发）。

另有一条「开源精选」流水线，每天另写一篇 GitHub 项目推荐。

## 流程

两条流水线共用并发组 `article-pipeline`（排队执行，互不取消），产物目录隔离。

### 日更（`daily.yml`，每天 08:00 UTC / 16:00 北京时间）

```
S1 search.py              Brave + HN/TechCrunch/ArXiv，精读正文 → output/collected.json
S2 plan.py                LLM 选题策划 → output/plan.json
S3 write.py               原创撰写 1800~3000 字 → output/YYYY-MM-DD.md + article.json
S4 gen_cover.py           Agnes 封面（失败则程序化概念图） → output/cover.jpg
S5 gen_article_images.py  文内配图 → output/images/
S6 fill_article.py        写入 jsDelivr CDN URL + thumb_url
S7 report.py              字数/章节/出处/配图/封面验收
S8 wechat-publish.js      存微信草稿箱
```

### 开源精选（`git-repo-daily.yml`，每天 09:00 UTC / 17:00 北京时间）

```
S1 git_search.py                 搜 GitHub，跳过已写过仓库 → output/git_collected.json
S2 git_research.py               README + 目录 + LLM 分析 → output/git_plan.json
S3 git_write.py                  开源精选正文 → output/git_YYYY-MM-DD.md + git_article.json
S4 git_cover.py                  封面 → output/git_cover.jpg
S5 gen_article_images.py --prefix git_  → output/git_images/
S6 fill_article.py --prefix git_
S7 report.py --prefix git_
S8 wechat-publish.js --file output/git_article.json
```

两条线都是先提交仓库、再发草稿，发布失败可按 git 状态重发。

## 配置

在仓库 `Settings → Secrets and variables → Actions` 添加：

### Secrets

- `LLM_API_KEY`：火山方舟 API Key（生图走同一把 Key 调 Agnes）
- `SEARCH_API_KEY`：Brave Search API Key
- `WX_SERVER`：wechat-publisher 中转地址
- `WX_SHARED_SECRET`：与中转服务 shared_secret 一致
- `WX_APPID` / `WX_APPSECRET`：公众号凭证
- `WX_UNLOCK_PASSWORD`：阿贝云调试域名门禁（可空）

### Variables

- `LLM_BASE_URL`：`https://ark.cn-beijing.volces.com/api/v3`
- `LLM_MODEL`：火山方舟接入点 ID
- `SEARCH_TOPICS`：检索主题，用 `|` 分隔
- `ARTICLE_AUTHOR`：作者名
- `ARTICLE_DIGEST`：摘要（可空）
- `CDN_HOST`：默认为 `cdn.jsdelivr.net`

GitHub 仓库搜索使用 Actions 自带的 `GITHUB_TOKEN`。

## 运行

- 日更 16:00、开源精选 17:00（北京时间）自动跑
- Actions 页可手动 `Run workflow`
- 本地：`pip install -r requirements.txt`，配齐环境变量后按脚本顺序执行

## 自定义

- 检索主题：改 Variable `SEARCH_TOPICS`
- 写作要求：改 `scripts/write.py` / `scripts/git_write.py` 的 prompt
- 策划要求：改 `scripts/plan.py` 的 `PLAN_PROMPT`
- 已推荐仓库：`output/git_featured.json`
- 配图风格：`scripts/image_style.py`（封面/文内提示词、禁文字、主题意象）
