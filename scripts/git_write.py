"""S3: Write a 【开源精选】 article about the featured repo.
Reads output/git_plan.json, outputs git_YYYY-MM-DD.md, output/article.json, output/images_meta.json.
Imports markdown_to_html from write.py to avoid duplication.
"""
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import llm
from write import markdown_to_html, extract_image_slots

WRITE_PROMPT = """你是资深公众号「开源精选」专栏作者。根据以下开源项目分析，写一篇推荐文章。

【项目分析】
{plan}

【README 摘要】
{readme}

【原创性要求】
- 必须是原创观点和表达，不要简单翻译 README
- 结合项目特点给出独到见解

【结构与风格】
- 结构：一句话导语 → 项目简介 → 核心特性 → 快速上手 → 技术亮点分析 → 适用场景与展望
- 目标读者：技术从业者、开源爱好者
- 风格：专业、清晰、有感染力
- 篇幅：**全文严格控制在 2400~3000 字**
- 提供增量价值：技术分析、对比评价、使用建议

【排版要求】
1. 每个核心章节用 `##` 小标题分段（小标题要具体、有吸引力）
2. 多用排版标记：**加粗**关键观点、>引用数据或言论、- 列要点
3. 在合适的章节标注 2~3 张配图位置：`![配图描述：一句话说明画面内容]`
4. 标题第一行用 `#`，其后空一行接正文
5. 结尾附上 GitHub 链接格式：`🔗 GitHub: https://github.com/XXX`

【输出格式】
第一行：标题（以 # 开头）
第二行起：正文 Markdown"""

def main():
    with open("output/git_plan.json", encoding="utf-8") as f:
        plan = json.load(f)
    with open("output/git_collected.json", encoding="utf-8") as f:
        collected = json.load(f)

    # Fetch README for the write prompt
    readme = ""
    try:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        repo_name = plan["repo"]["full_name"]
        import base64, urllib.request
        url = f"https://api.github.com/repos/{repo_name}/readme"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "daily-ai-article/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        readme = base64.b64decode(data["content"]).decode("utf-8", errors="replace")[:4000]
    except Exception as e:
        print(f"  README fetch for write failed: {e}")

    base_prompt = WRITE_PROMPT.format(
        plan=json.dumps(plan, ensure_ascii=False)[:4000],
        readme=readme[:3000],
    )

    def wc(md):
        body = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith("#"))
        return len(re.sub(r"\s", "", body))

    # Write with retry on word count
    max_attempts = 3
    article = None
    last_wc = 0
    for attempt in range(max_attempts):
        prompt = base_prompt
        if attempt > 0:
            prompt += f"\n\n【上次生成不合格】上次全文 {last_wc} 字。请压缩到 2400~3000 字，保留所有小标题和排版标记。"
        article = llm.chat([{"role": "user", "content": prompt}], temperature=0.8, max_tokens=4096).strip()
        last_wc = wc(article)
        print(f"write attempt {attempt+1}/{max_attempts}: {last_wc} chars")
        if 1800 <= last_wc <= 3200:
            break
        if attempt < max_attempts - 1:
            print(f"  word count {last_wc} out of range, retrying...")

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

    # Save markdown
    md_path = f"output/git_{date.today()}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(article)

    # Image slots
    image_slots = extract_image_slots(body)
    with open("output/images_meta.json", "w", encoding="utf-8") as f:
        json.dump(image_slots, f, ensure_ascii=False, indent=2)

    # Build article.json
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
    with open("output/article.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"article written: {md_path} | payload: output/article.json | images: {len(image_slots)}")
    print(f"  title: {title}")

if __name__ == "__main__":
    main()
