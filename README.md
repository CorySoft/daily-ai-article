# 每日 AI 公众号文章

定时全网检索 → AI 策划 → AI 原创撰写 → 配图 → 自检验收 → 存入公众号草稿箱（不群发）。

另有一条「开源精选」流水线，每天另写一篇 GitHub 项目推荐。

## 流程

两条流水线共用并发组 `article-pipeline`（排队执行，互不取消），产物目录隔离。

### 日更（`daily.yml`，每天 00:00 UTC / 08:00 北京时间）

```
S1 search.py              Brave + Hacker News + TechCrunch + ArXiv + GitHub Trending，精读正文 → output/collected.json
S2 plan.py                按热度分档过滤 + LLM 选题策划 → output/plan.json
S3 write.py               原创撰写 1800~3400 字（目标 2400~3200）→ output/YYYY-MM-DD.md + article.json
S4 gen_cover.py           Agnes 封面（失败则程序化概念图） → output/cover.jpg
S5 gen_article_images.py  文内配图 → output/images/
S6 fill_article.py        写入 jsDelivr CDN URL + thumb_url
S7 report.py              字数/章节/出处/配图/封面验收
S8 wechat-publish.js      存微信草稿箱
```

### 开源精选（`git-repo-daily.yml`，每天 01:00 UTC / 09:00 北京时间）

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

## 选题是怎么被卡住 hotness 的（S2 `plan.py`）

之前的失败模式不是写不出，而是**选题本身不热**：抓回来的料只要"和 AI 沾边"就能被选中，
于是产出一堆谁都能猜到的泛泛文章。现在 S2 在交给 LLM 之前先按信源硬分档：

| 档位 | 判据 |
|---|---|
| **A** | Hacker News `score ≥ 80`；GitHub Trending `trending_rank ≤ 5`（缺 rank 时回退今日新增星数 ≥ 1000） |
| **B** | HN `score ≥ 40`；Trending `rank ≤ 10`（或新增星 ≥ 200） |
| **C** | ArXiv 及其它信源：**3 天内**发布的才算 |

- A 档不足 3 条才放宽到 B，B 也不够才放宽到 C —— **放宽是逐级降级的，不是默认全收**
- LLM 必须在输出里回填 `source_title` / `source_url`，脚本校验该 URL 确实出现在被选档位的
  料里（比较时忽略 `#`/`&`/末尾斜杠，允许前 40 字符前缀匹配）；**锚不上就判失败**
- 校验失败重试一次（temperature 降到 0.3），两次都不过 `sys.exit(1)` —— 宁可流水线红，
  也不要发一篇没有真实热点锚定的稿子
- 日志会打印 `热度门槛生效: A档 N 条（B x / C y 已剔除）`，跑完一眼能看出门槛有没有在干活

热度的来源侧：`search.py` 抓 GitHub Trending 时会记录 `trending_rank`（页面顺序）、
`stars`（总数）与今日新增星数，`hotness = 今日新增 or 总数`；`rank_by_freshness`
对数衰减 × `log1p(hotness)` 加权，越新越热排得越前。

## 配置

在仓库 `Settings → Secrets and variables → Actions` 添加：

### Secrets

- `LLM_API_KEY`：**Agnes（`apihub.agnes-ai.com`）** 的 API Key。写稿/策划与生图**共用同一把 Key**
  （`llm.py` 的 `base_url` 默认值就是 `https://apihub.agnes-ai.com/v1`，
  `gen_cover.py` 的 `AGNES_API_URL` 是 `.../v1/images/generations`）。
  > 旧文档这里写"火山方舟 API Key"是 `1ce945e` 之前直连 Ark 时代的说法（`ddec9a8` 起默认走
  > `ark.cn-beijing.volces.com`，`1ce945e` 把默认换成了 Agnes），现在信源已经是 Agnes；
  > 中转服务里那个 `/llm/` 代理硬编码的 `ark.cn-beijing.volces.com` 跟本流水线无关，别把它们混起来。
- `SEARCH_API_KEY`：Brave Search API Key
- `WX_SERVER`：wechat-publisher 中转地址
- `WX_SHARED_SECRET`：与中转服务 shared_secret 一致
- `WX_APPID` / `WX_APPSECRET`：公众号凭证
- `WX_UNLOCK_PASSWORD`：阿贝云调试域名门禁（可空）

> 旧文档在这里还列过一个 `NOTIFY_WEBHOOK`（"流水线失败时 POST 通知"）—— **现在配了也没用**：
> 失败通知步骤由 `b703dd5` 加进两条 workflow（`if: failure()` + 一段 POST run 链接的 Python），
> 又在下一天的 `c5ac311 chore: remove failure notification step from workflows` 里整体删掉了
> （每份 workflow -25 行）。所以现在两条 workflow 和 `scripts/` 全文都搜不到 `NOTIFY`/`webhook`，
> 失败只能靠 GitHub 自己的通知设置/Actions 页面。要恢复推送就照 `c5ac311` 的反向 diff 把那个
> step 加回来，再配 Secret —— 别只配 Secret。

### Variables

- `LLM_BASE_URL`：`https://apihub.agnes-ai.com/v1`（生产在 Actions Variables 注入）
- `LLM_MODEL`：`agnes-3.0-flash`（生产在 Actions Variables 注入）
- `SEARCH_TOPICS`：检索主题，用 `|` 分隔
- `ARTICLE_AUTHOR`：作者名
- `ARTICLE_DIGEST`：摘要（可空）
- `CDN_HOST`：workflow 里的**默认值**是 `cdn.jsdelivr.net`，但生产 Variable 实际设成了
  `testingcf.jsdelivr.net`（Cloudflare 测试节点，绕开 `cdn.jsdelivr.net` 的缓存/区域问题）。
  想改回默认就在 Actions Variables 里删掉这个变量，别只改 workflow 默认值 —— 那行会被 Variable 覆盖。

GitHub 仓库搜索使用 Actions 自带的 `GITHUB_TOKEN`。

## 运行

- 定时：**日更 00:00 UTC = 北京 08:00**，**开源精选 01:00 UTC = 北京 09:00**
  （`daily.yml` / `git-repo-daily.yml` 的 `cron` 就是这两行，仓库里以 UTC 写）
  > ⚠️ 实测 GitHub 的 scheduled 触发**常年晚 4~5.5 小时**（近两周记录是 03:25~05:30 UTC，
  > 即北京 11:25~13:30 才开跑）。这是 GitHub Actions 调度排队，不是本项目的问题；
  > 但"几点出稿"要按实际开始时间算，别按 cron 字面值安排。旧文档写的"北京 16:00 / 17:00"
  > 是 commit `5e22329` 之前那版 cron（`0 8 * * *` UTC）的遗留，改到 `0 0 * * *` 后 README 没跟上。
- Actions 页可手动 `Run workflow`
- 本地：`pip install -r requirements.txt`，配齐环境变量后按脚本顺序执行
  **且必须从仓库根目录执行**（`python scripts/write.py`，不是 `cd scripts && python write.py`）：
  所有产物路径都是相对的 `output/...`，其中 `git_search.py` 的
  `FEATURED_PATH = "output/git_featured.json"` 尤其致命 —— 换个工作目录它就看不到
  "已推荐过哪些仓库"，会把写过的仓库反复再写一遍，而且不会报错。

## 自定义

- 检索主题：改 Variable `SEARCH_TOPICS`
- 写作要求：改 `scripts/write.py` / `scripts/git_write.py` 的 prompt
- 策划要求：改 `scripts/plan.py` 的 `PLAN_PROMPT`
- 已推荐仓库：`output/git_featured.json`
- 配图风格：`scripts/image_style.py`（封面/文内提示词、禁文字、主题意象）
