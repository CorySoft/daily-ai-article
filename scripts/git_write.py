"""S3: Write a 【开源精选】 article about the featured repo.
Reads output/git_plan.json, outputs git_YYYY-MM-DD.md, output/git_article.json, output/git_images_meta.json.
Imports markdown_to_html from write.py to avoid duplication.
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import llm
from util import word_count as wc
from util import ACCEPT_WORD_MIN, ACCEPT_WORD_MAX, is_complete
from util import recent_outputs, risk_flags, risk_verdict, style_issues
from util import retry_hint
from write import markdown_to_html, extract_image_slots

FEATURED_PATH = "output/git_featured.json"


def mark_featured(full_name):
    """记入已推荐清单（owner/repo 大小写不敏感）。失败退场时也要记账，
    否则明天 pick_repo 会选中同一个仓库、在同一处再失败一次。"""
    if not full_name:
        return
    featured = []
    if os.path.exists(FEATURED_PATH):
        with open(FEATURED_PATH, encoding="utf-8") as f:
            featured = json.load(f)
    if all((item.get("full_name") or "").lower() != full_name.lower() for item in featured):
        featured.append({"full_name": full_name, "date": date.today().isoformat()})
        with open(FEATURED_PATH, "w", encoding="utf-8") as f:
            json.dump(featured, f, ensure_ascii=False, indent=2)

STRUCTURES = [
    "一句话导语 → 它解决了什么别人没解决的问题 → 核心机制拆解 → 上手成本与依赖 → 什么情况下别用 → 与同类项目的取舍",
    "从一个具体场景切入 → 为什么现有方案在这个场景下不够用 → 这个项目的做法 → 关键实现细节 → 跑起来要几步 → 局限性说清楚",
    "项目缘起（作者/issue/commit 线索）→ 设计上的关键抉择 → 与主流方案的差异点 → 真实使用中的坑 → 适合谁、不适合谁",
    "先看它能做到什么（可验证的效果）→ 怎么做到的 → 代码组织与工程取向 → 性能/资源/安全上的注意项 → 后续可期待的方向",
    "反直觉的切入点（它故意不做什么）→ 由此暴露的行业默认做法 → 该项目的替代路径 → 迁移成本 → 一句话结论",
]


def structure_for(day):
    """按日期轮换结构，避免「项目简介/核心特性/快速上手/技术亮点/适用场景/结语」
    这套模板连用两个月（实测 62 篇里 52 篇出现「快速上手」、40 篇「核心特性」）。"""
    return STRUCTURES[int(day.strftime("%Y%m%d")) % len(STRUCTURES)]


WRITE_PROMPT = """你是资深公众号「开源精选」专栏作者。根据以下开源项目分析，写一篇推荐文章。

【项目分析】
{plan}

【README 摘要】
{readme}

【原创性要求】
- 必须是原创观点和表达，不要简单翻译 README
- 结合项目特点给出独到见解
- README 里的功能罗列不足以撑起全文：必须交代「为什么是它」「什么时候别用」，并给出可验证的细节

【结构与风格】
- 结构（本轮必须按这套来，不要退回「核心特性/快速上手/技术亮点分析/适用场景与展望/结语」那套老骨架）：{structure}
- 目标读者：技术从业者、开源爱好者
- 风格：专业、清晰、有感染力
- 篇幅：**全文严格控制在 2400~3200 字**（宁少勿多；低于 2200 字或超过 3400 字都判失败）
- 提供增量价值：技术分析、对比评价、使用建议
- 填充语黑名单（全文合计 ≤2 次）：想象一下、值得注意的是、让我们、综上所述、首先，/其次，/最后， 三连式

【排版要求】
1. 每个核心章节用 `##` 小标题分段（小标题要具体、有吸引力；
   禁用「结语」「总结」「展望」「思考」「引言」「核心特性」「快速上手」这类通用名，结尾也要有具体论断）
   - 不要沿用最近几篇开源精选的小标题措辞，同一栏目连续出现同套结构即为不合格
2. 多用排版标记：**加粗**关键观点、>引用数据或言论、- 列要点
3. 在合适的章节标注 2~3 张配图位置：`![配图描述：一句话说明画面内容]`
    - 描述必须是可绘制的物体/场景/材质/光影，不要写 GitHub 截图、Star 按钮、文档站界面、徽章
    - 不要出现文字、数字、Logo；用隐喻表达项目特质
4. 标题第一行用 `#`，其后空一行接正文
5. 结尾附上 GitHub 链接格式：`🔗 GitHub: https://github.com/XXX`

【输出格式】
第一行：标题（以 # 开头）
第二行起：正文 Markdown"""

def main():
    with open("output/git_plan.json", encoding="utf-8") as f:
        plan = json.load(f)

    repo = plan.get("repo", {})
    risky = risk_flags(repo.get("full_name", ""), repo.get("description", ""),
                       " ".join(repo.get("topics", []) or []))
    if risky:
        # git_search 已经拦过一道；这里是防止拿旧的 git_collected.json 重跑时绕过门槛
        print(f"ERROR: 仓库命中风险项 {risky}，拒绝成稿：{repo.get('full_name')}", file=sys.stderr)
        sys.exit(1)

    readme = ""
    try:
        import base64
        import github_api
        repo_name = plan["repo"]["full_name"]
        data = github_api.get(f"/repos/{repo_name}/readme")
        readme = base64.b64decode(data["content"]).decode("utf-8", errors="replace")[:4000]
    except Exception as e:
        print(f"  README fetch for write failed: {e}")
    if not readme.strip():
        # 没有 README 就只能靠仓库名想象功能 —— 这种稿子发出去一定是编的
        print(f"ERROR: 拿不到 {plan.get('repo', {}).get('full_name')} 的 README，拒绝凭想象成稿",
              file=sys.stderr)
        sys.exit(1)

    base_prompt = WRITE_PROMPT.format(
        plan=json.dumps(plan, ensure_ascii=False)[:4000],
        readme=readme[:3000],
        structure=structure_for(date.today()),
    )

    recent_md, recent_titles = recent_outputs(days=5, kind="git")
    max_attempts = 3
    article = None
    last_wc = 0
    problems = []
    for attempt in range(max_attempts):
        prompt = base_prompt
        if attempt > 0:
            prompt += ("\n\n【上次生成不合格】" + retry_hint(
                last_wc, "保留小标题和排版标记。") +
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

    # fail-fast: 3 次仍不达标则终止流水线，避免白烧 S4/S5 的生图 API
    if not (ACCEPT_WORD_MIN <= last_wc <= ACCEPT_WORD_MAX and is_complete(article)):
        print(
            f"ERROR: 3 attempts, word count {last_wc} outside {ACCEPT_WORD_MIN}~{ACCEPT_WORD_MAX} or truncated, aborting",
            file=sys.stderr,
        )
        sys.exit(1)
    if problems:
        print(f"WARNING: 排版仍雷同，未再重试以免耽误发布: {'；'.join(problems)}", file=sys.stderr)

    # Split title
    lines = article.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        title = lines[0].lstrip().lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()
    else:
        title = f"开源精选 | {plan.get('topic', 'Unknown')}"
        body = article

    # Ensure 【开源精选】 prefix
    if "开源精选" not in title:
        title = f"开源精选 | {title}"

    # 到了成稿才认出「这仓库不能推」时就地停：别烧 S4/S5 的生图，也别留给 S7 才发现。
    # 顺手记进 git_featured —— 这类仓库名字通常是干净的，S1 的 risk 门槛拦不住，
    # 不记账明天还会选中它，然后原地再失败一次。
    hard, _ = risk_verdict(
        [repo.get("full_name", ""), repo.get("description", ""),
         " ".join(repo.get("topics", []) or [])],
        [title], True)
    if hard:
        mark_featured(repo.get("full_name", ""))
        print(f"ERROR: 成稿标题命中内容安全红线 {hard}，拒绝发布：{repo.get('full_name')}"
              f"（已记入 git_featured，不会再被选中）", file=sys.stderr)
        sys.exit(1)

    # Save markdown
    md_path = f"output/git_{date.today()}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(article)

    image_slots = extract_image_slots(body)
    with open("output/git_images_meta.json", "w", encoding="utf-8") as f:
        json.dump(image_slots, f, ensure_ascii=False, indent=2)

    articles = {
        "title": title,
        "author": os.environ.get("ARTICLE_AUTHOR", "CorySoft"),
        "digest": f"开源精选 | {plan.get('tagline', plan.get('topic', ''))}",
        "content": markdown_to_html(body),
    }

    payload = {
        "draft": True,
        "articles": [articles],
    }
    with open("output/git_article.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    mark_featured(plan.get("repo", {}).get("full_name"))

    print(f"article written: {md_path} | payload: output/git_article.json | images: {len(image_slots)}")
    print(f"  title: {title}")

if __name__ == "__main__":
    main()
