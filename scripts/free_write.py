"""S3: Write a 【免费额度观察】 article about the planned official free tier.

Reads output/free_plan.json + output/free_collected.json,
writes output/free_YYYY-MM-DD.md, free_images_meta.json, free_article.json.
Reuses write.py's markdown -> WeChat HTML renderer.
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import llm
from free_search import mark_featured, normalize_url
from util import ACCEPT_WORD_MIN, ACCEPT_WORD_MAX, is_complete
from util import recent_outputs, risk_verdict, retry_hint, slim_collected, style_issues
from util import word_count as wc
from write import extract_image_slots, markdown_to_html

STRUCTURES = [
    "先说这份额度到底能干什么 → 官方条款逐条拆（谁能用/给多少/多久）→ 与同类免费层对比 → 容易被忽略的限制 → 到期后怎么选 → 一句可执行的判断",
    "从一个真实开发场景切入 → 为什么这次的免费层值得看 → 额度与资格核对 → 隐性成本与边界 → 什么时候别折腾 → 行动清单",
    "厂商为什么现在给免费层（商业动机）→ 条款里藏着的条件 → 和上一版免费层的变化 → 真实可用的上限 → 适合谁、不适合谁",
    "先给结论（值不值得花时间）→ 证据：官方数字与期限 → 限制逐项验证 → 与付费档的临界点 → 风险与合规提醒 → 下一步建议",
    "反直觉的切入点（免费层最贵的地方不是钱）→ 由此看厂商的获客逻辑 → 条款细节 → 读者实际能拿到什么 → 什么时候应该付费",
]


def structure_for(day):
    return STRUCTURES[int(day.strftime("%Y%m%d")) % len(STRUCTURES)]


WRITE_PROMPT = """你是资深公众号「免费额度观察」专栏作者。根据以下已核实的官方免费层策划，写一篇原创中文文章。

【策划】
{plan}

【检索素材】（仅作事实核对，不得照抄标题段落）
{collected}

【本轮结构】必须按这套骨架展开，不要退回「核心价值/快速上手/适用场景/结语」那类模板：
{structure}

【硬要求】
- 必须写清：额度数字、适用对象、有效期、官方条款链接、限制与坑；每条事实都能对应到【策划】或素材
- 只介绍厂商官方正常注册渠道；**禁止**出现批量注册、接码、养号、共享/合租账号、虚构身份、绕过地区限制等操作建议
- 标题与正文用「免费额度 / 免费层 / 官方试用」这类中性表述，不要写「薅羊毛」「免费领会员」这类词
- 无法核实的信息不得写成事实；素材冲突时在正文说明
- 原创表达，不复述官方通稿，每章都要推进新信息或新判断
- 填充语黑名单（全文合计 ≤2 次）：想象一下、值得注意的是、让我们、综上所述、首先，/其次，/最后， 三连式
- 篇幅：**全文严格控制在 2400~3200 字**（低于 2200 或超过 3400 判失败）

【排版要求】
1. 每个核心章节用 `##` 小标题（具体、有信息量，禁用「结语」「总结」「展望」「思考」「引言」），结尾也要有具体论断
2. 多用排版标记：**加粗**关键判断、>引用条款或数字、- 列要点
3. 标注 2~3 张配图位，格式：`![配图描述：一句话说明画面内容]`
   - 描述必须可绘制（物体/场景/材质/光影），不要写截图、界面、Logo、带字屏幕、二维码、按钮
4. 标题第一行用 `#`，其后空一行接正文；结尾附官方条款链接

【输出格式】
第一行：标题，以 # 开头
第二行起：正文 Markdown"""


def main():
    with open("output/free_plan.json", encoding="utf-8") as f:
        plan = json.load(f)
    try:
        with open("output/free_collected.json", encoding="utf-8") as f:
            collected = json.load(f)
    except OSError:
        collected = {}

    offer = plan.get("offer") or {}
    official_url = str(offer.get("official_url") or "")
    hard, _ = risk_verdict(
        [offer.get("name", ""), offer.get("provider", ""), official_url,
         plan.get("source_title", ""), plan.get("source_url", "")],
        [plan.get("topic", ""), plan.get("angle", ""), plan.get("core_view", "")],
        True)
    if hard:
        # 跟 git_write 一样：失败也要记账，否则明天还会选中同一个条款原地再炸
        mark_featured(official_url or plan.get("source_url"))
        print(f"ERROR: 选题命中内容安全红线 {hard}，拒绝成稿并已记入 free_featured", file=sys.stderr)
        sys.exit(1)

    base_prompt = WRITE_PROMPT.format(
        plan=json.dumps(plan, ensure_ascii=False)[:4000],
        collected=slim_collected(collected, max_chars=4000)[:4000],
        structure=structure_for(date.today()),
    )

    recent_md, recent_titles = recent_outputs(days=5, kind="free")
    max_attempts = 3
    article = None
    last_wc = 0
    problems = []
    for attempt in range(max_attempts):
        prompt = base_prompt
        if attempt > 0:
            prompt += ("\n\n【上次生成不合格】" + retry_hint(
                last_wc, "保留所有 ## 小标题、加粗、列表、引用和 2~3 个配图位；"
                         "正文中须内嵌官方条款 URL。") +
                ("另外：" + "；".join(problems) if problems else ""))
        article = llm.chat([{"role": "user", "content": prompt}], temperature=0.8, max_tokens=8192).strip()
        last_wc = wc(article)
        problems = style_issues(article, recent_md, recent_titles)
        print(f"write attempt {attempt+1}/{max_attempts}: {last_wc} chars"
              + (f" | 排版问题: {'；'.join(problems)}" if problems else ""))
        if ACCEPT_WORD_MIN <= last_wc <= ACCEPT_WORD_MAX and is_complete(article) and not problems:
            break
        if attempt < max_attempts - 1:
            print("  字数越界/疑似截断/排版雷同，重试中...")

    if not (ACCEPT_WORD_MIN <= last_wc <= ACCEPT_WORD_MAX and is_complete(article)):
        print(f"ERROR: 3 attempts, word count {last_wc} outside "
              f"{ACCEPT_WORD_MIN}~{ACCEPT_WORD_MAX} or truncated, aborting", file=sys.stderr)
        sys.exit(1)
    if problems:
        print(f"WARNING: 排版仍雷同，未再重试以免耽误发布: {'；'.join(problems)}", file=sys.stderr)

    lines = article.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        title = lines[0].lstrip().lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()
    else:
        title = f"免费额度 | {plan.get('topic', 'Unknown')}"
        body = article

    if "免费额度" not in title:
        title = f"免费额度 | {title}"

    hard, _ = risk_verdict([offer.get("name", ""), official_url], [title], True)
    if hard:
        mark_featured(official_url or plan.get("source_url"))
        print(f"ERROR: 成稿标题命中内容安全红线 {hard}，拒绝发布：{title}", file=sys.stderr)
        sys.exit(1)

    os.makedirs("output", exist_ok=True)
    md_path = f"output/free_{date.today()}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(article)

    image_slots = extract_image_slots(body)
    with open("output/free_images_meta.json", "w", encoding="utf-8") as f:
        json.dump(image_slots, f, ensure_ascii=False, indent=2)

    articles = {
        "title": title,
        "author": os.environ.get("ARTICLE_AUTHOR", "CorySoft"),
        "digest": f"免费额度观察 | {plan.get('topic', '')}",
        "content": markdown_to_html(body),
        "need_open_comment": 1,
        "only_fans_can_comment": 0,
    }
    with open("output/free_article.json", "w", encoding="utf-8") as f:
        json.dump({"draft": True, "articles": [articles]}, f, ensure_ascii=False, indent=2)

    mark_featured(official_url or plan.get("source_url") or "")
    if normalize_url(official_url) != normalize_url(plan.get("source_url")):
        # 条款页与来源页不同也一并记账，避免明天从另一条素材再选中同一家
        mark_featured(plan.get("source_url") or "")

    print(f"article written: {md_path} | payload: output/free_article.json | images: {len(image_slots)}")
    print(f"  title: {title}")


if __name__ == "__main__":
    main()
