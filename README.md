# 每日 AI 公众号文章

定时全网检索 → AI 策划 → AI 原创撰写 → 配图 → 自检验收 → 存入公众号草稿箱（不群发）。

另有一条「开源精选」流水线，每天另写一篇 GitHub 项目推荐。

## 流程

两条流水线共用并发组 `article-pipeline`（排队执行，互不取消），产物目录隔离。

### 日更（`daily.yml`，每天 00:00 UTC / 08:00 北京时间）

```
S0 unittest (scripts/)     纯离线门槛测试，先于任何外部调用，不烧 API
S1 search.py              Brave + Hacker News + TechCrunch + ArXiv + GitHub Trending，精读正文 → output/collected.json
S2 plan.py                按热度分档过滤 + LLM 选题策划 → output/plan.json
S3 write.py               原创撰写 2200~3400 字（提示词要 2400~3200）→ output/YYYY-MM-DD.md + article.json
S4 gen_cover.py           Agnes 封面（失败则程序化概念图） → output/cover.jpg
S5 gen_article_images.py  文内配图 → output/images/
S6 fill_article.py        写入 jsDelivr CDN URL + thumb_url
S7 report.py              字数/章节/出处/配图/封面/截断/内容安全验收
S8 wechat-publish.js      存微信草稿箱
```

### 开源精选（`git-repo-daily.yml`，每天 01:00 UTC / 09:00 北京时间）

```
S0 unittest (scripts/)             同一条离线测试
S1 git_search.py                   搜 GitHub → 质量/风险硬门槛（`gate()`）→ 跳过已写过仓库 → output/git_collected.json
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

## 内容安全与质量门槛（2026-11-06 语料复盘后加的）

复盘了 `output/` 里全部 131 篇（69 日更 + 62 开源精选）。字数其实是健康的
（日更中位 2647、开源精选 2879，无一超 3400），去重也没坏（67 条 `git_featured` 记录零重复）；
真正的问题是**推荐了不该推荐的项目**和**长得都一样**。

### P0：开源精选曾把违规仓库写成待发草稿

复盘全部 67 条 `git_featured` 记录 + 62 篇成稿，**新红线会拦下这些**：

| 仓库 / 稿子 | 谁拦的 |
|---|---|
| `ctdal/cve-2026-41940-PoC`、`eness/php2shell-CVE-...` | S1 `gate()`（仓库名即 PoC） |
| `david-silvalab1993i0/Roblox-Aimbot-...`、`DrWhax/unfairplay` | S1 `gate()`（外挂） |
| `wideeyededi/uncensored-nsfw-ai-video-api` | S1 `gate()`（涉黄） |
| `Nucleusanwish/microsoft-office` | S1 `gate()` 分段匹配 + S7 |
| `worldonlyu/Google_AI_Pro_2Year_ZeroCost_Auto`（11-06 已发） | S3/S7 标题「薅羊毛」→ 灰产 |
| `MouseAngular/KMS-Pico`（10-13）、`VarnishTrackPrize/ultra-Iso`（10-06） | 名字干净，只有 S3/S7 看成稿标题才知道是伪装恶意项目 |

根因是上一版检索式：`stars:>30` + `created:>最近3天` + "3 天内有 push" 加权 ×1.8 ——
这套条件不是在找好项目，是在专门捞新注册、刷星的灰产空壳。
注意这些稿子的**内容**大多是正当的安全分析：模型自己认出仓库有问题、改写成"避坑"文，
但推荐栏目里出现后门样本 + 仓库链接本身就是一次风险暴露。所以现在是硬拦，不看语气。

现在是六道防线：

| 位置 | 拦什么 |
|---|---|
| `plan._validate()`（日更 S2） | 选题层面先过一遍红线（`source_title`/`source_url` + `topic`/`angle`/`core_view`），命中就把问题拼进重试提示强制换题，两次不过 `exit 1` —— 比等 S7 拦下省一整条流水线的钱 |
| `write.py` 成稿后（日更 S3） | 标题跑一次 `risk_verdict(recommend=False)`，硬拦就 `exit 1`，别去烧 S4/S5 的生图 |
| `git_search.gate()` | 单仓库硬门槛：`stars ≥ 200`、`forks ≥ 3`、`size ≥ 40KB`（小于此多半只有一份 README）、必须有 SPDX 许可证、非 fork / 非归档 / 有描述、避开 `awesome-`/教程/面试题/刷题 类，最后过 `risk_flags()` |
| `git_search.pick_repo()` | 新鲜度加权 0.8 → 0.3；候选**全部**已推荐过就 `exit 1`，不再回收旧选题 |
| `git_write.main()` 开头 | 再用 `risk_flags()` 查一遍 `repo` 的 `full_name`/`description`/`topics`（防止拿旧 `git_collected.json` 重跑绕过 S1）；**README 取不到就拒绝成稿** —— 没有 README 只能靠仓库名想象功能，那种稿子一定是编的 |
| `git_write.main()` 成稿后 | 对**标题**跑 `risk_verdict(recommend=True)`：伪装成正常项目的恶意仓库（名字干净、S1 看不出来）在这一步被拦，`exit 1` 前先 `mark_featured()` 记账，免得明天选中同一个再原地失败一次，也省掉 S4/S5 的生图钱 |
| `report.py`（S7） | 最后一道：`title`/`topic`/`angle`/`core_view` + 仓库元信息再查一次红线，同时复查"全文未被截断" |

红线词族在 `util.RISK_PATTERNS`：涉黄 / 攻击·漏洞利用 / 游戏作弊 / 盗版·破解 / 灰产 / 仿冒品牌。
匹配时**整串和每个 `/` 分段都试** —— `Nucleusanwish/microsoft-office` 只有按分段匹配才拦得住
（品牌规则是 `^…$`，否则会被 owner 段挡掉）。确属误伤时不要放宽门槛：人工核对该稿后
直接用 `client/` 发布即可，`report.py` 的告警里写着这句。

灰产那一类是**复盘当天现网稿子时补的**：`git_2026-11-06.md`《从"薅羊毛"到系统化套利：解构 Google
AI Pro 两年免费脚本的攻防逻辑》推荐的是 `worldonlyu/Google_AI_Pro_2Year_ZeroCost_Auto`
（自动绑免税卡、叠三次免费周期），旧词表一条都不命中。现在补了
`薅羊毛 / 免税卡 / 批量注册 / 养号 / 代挂 / 刷(播放量|粉丝|点赞|评论|单) / 免费(领|刷|开通)(会员|账号) / trial abuse`。

### 推荐口径与报道口径要分开（`util.risk_verdict`）

一刀切会把正当选题打死：日更 2026-08-21 那篇《当代码仓库变成特洛伊木马：AI 时代供应链攻击的暗面》
是正常的安全新闻，标题里的「木马」不该判死。所以 S7 分两个面：

- **subject**（被推荐/被报道的对象：仓库名、描述、topics、素材标题与 URL）
- **editorial**（我们写出来的话：标题、`topic`、`angle`、`core_view`）

开源精选线（`recommend=True`）两类里**任何**命中都硬拦 —— 我们是在让读者去用这个东西。
日更线（`recommend=False`）只硬拦 `涉黄 / 游戏作弊 / 盗版·破解 / 灰产 / 仿冒品牌`，
「攻击/漏洞利用」降为 `NOTE` 放行并写进 `report.json` 的 `risk_notes`：
讲 CVE、讲 npm 恶意包本来就是科技新闻的常态版面，一刀切等于自废武功。

拿 131 篇存量稿的标题重放这套口径：**硬拦 3 篇**（全是开源精选：18+ API、UnfairPlay、KMS-Pico），
**告警放行 1 篇**（日更那篇供应链木马），当天新发的《从"薅羊毛"到系统化套利》按新词表也会硬拦 ——
除了"标题带木马的日更新闻"这一类，没有误伤。

> 已知会被拦下的正当情形：`git_2026-10-13.md` 那种「警惕 KMS-Pico：…成为木马的伪装外衣」
> —— 推荐栏目里的安全科普照样被 editorial 打死。这是故意的
> （`test_defensive_security_title_is_flagged_too` 把它钉住了）：S7 分不清"教读者用外挂"
> 和"提醒读者别装"，宁可红一次让人来看。别为了让它自动过而删词。

### 引用必须锚定到选题本身

旧的 `write.py` 在正文没有 URL 时，从 `collected` 里抓**前 3 条**拼成「参考来源」，
与本事件无关。实测 10 月以来 31% 的稿子因此挂着毫不相干的域名（讲 YC 掌门人烧 20 万美元，
末尾链的却是个光盘镜像工具仓库）。现在 `_citation_urls()` 只认 `plan.source_url`
（S2 已按热度档位校验过它确实对应选中素材），锚点缺失才退回素材里第一条，**绝不散弹**。

### `is_complete()` 的语义

先剥掉文末的引用行（`> 参考来源：…`、`Sources:`、`（来源：…）`）、纯链接行
（`🔗 GitHub: https://…`）和 `---` 分隔线，再看剩下最后一句有没有句末标点，并要求 `##` ≥ 3。
省略号结尾算截断；加粗结尾（`**钥匙握在你手里。**`）算完稿。
注意注入「参考来源」必须发生在计数与截断判定**之前**，否则 S3 量注入前、S7 查注入后，
贴着上限的稿子会被来源行顶出区间。

### 千篇一律（告警，不判死）

`util.style_issues()` 查三样：套话（`BOILERPLATE`）> 4 处、与近 5 篇相同小标题 > 1 个、
标题句式与近期文章**全部**同为「主标题：副标题」。结果会拼进重试提示；
3 次后仍雷同只打 `WARNING`，不让流水线红 —— 排版雷同不值得耽误发布。
`git_write.py` 另加了 `STRUCTURES`：按日期取模轮换 5 套骨架，禁用「核心特性/快速上手/技术亮点/
适用场景与展望/结语」那套连用两个月的老模板 —— 62 篇开源精选里 **53 篇**有小标题含「快速上手」、
61 篇含「适用场景」；日更线 69 篇里 **49 篇**带「结语」。

字数硬下限 `ACCEPT_WORD_MIN` 从 1800 提到 **2200**（语料里 5 篇不足 2000 字全程绿灯）；
提示词要的区间仍是 2400~3200，`test_util.ThresholdTest` 会核对两边文案与常量一致。

### 跑测试

```
python -m unittest discover -s scripts -t scripts     # 51 项，纯离线，不碰任何外部 API
```

两条 workflow 都在 S1 之前加了 `Unit tests (offline gates)` 步骤。加这一步的直接理由：
`f5db70c` 把「参考来源」注入挪到验收之前，而 `is_complete` 当时不认引用尾巴，
把 27/30 篇判成"未完稿" —— 测试套件早就写好了，CI 一次都没跑过，所以它是静悄悄上线的。


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
- 开源精选搜什么仓库：`scripts/git_search.py` 的 `QUERIES_BASE`；卡多严：同文件
  `MIN_STARS` / `MIN_FORKS` / `MIN_SIZE_KB` / `SKIP_KEYWORDS`
- 内容安全红线：`scripts/util.py` 的 `RISK_PATTERNS`（**只该加，不该减**）
- 写作要求：改 `scripts/write.py` / `scripts/git_write.py` 的 prompt
- 开源精选的结构：`scripts/git_write.py` 的 `STRUCTURES`（按日期取模轮换）
- 字数/套话/雷同阈值：`scripts/util.py` 的 `ACCEPT_WORD_*` / `TARGET_WORD_*` /
  `MAX_BOILERPLATE` / `MAX_SECTION_OVERLAP`
- 策划要求：改 `scripts/plan.py` 的 `PLAN_PROMPT`
- 已推荐仓库：`output/git_featured.json`
- 配图风格：`scripts/image_style.py`（封面/文内提示词、禁文字、主题意象）
