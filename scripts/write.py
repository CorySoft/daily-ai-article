import argparse
import json
import os
import re
from datetime import date
import llm

WRITE_PROMPT = """你是资深公众号作者。根据选题策划，写一篇原创中文公众号文章。

【策划】
{plan}

【检索素材】（仅作研究资料，禁止作为改写模板）
{collected}

【原创性硬约束】
- 素材仅作研究，禁止复制其标题/段落/结论、禁止近义改写、禁止沿用其结构
- 必须重新创作全部正文与标题，形成独立观点、结构、表达
- 事实/数据/产品名可保留，但须重组与解释
- 引用关键数据/言论须标注来源（来源URL）
- 无法确认的信息不得写成事实；素材多源冲突须在正文说明差异

【结构与风格】
- 结构：标题 → 悬念导语 → 背景 → 核心章节(3~5) → 案例/数据/对比 → 读者影响 → 独立分析 → 有力结尾
- 目标读者：普通大众、科技与 AI 从业者
- 风格：专业、清晰、有观点
- 篇幅：**全文严格控制在 2200~2800 字**（宁少勿多，超过 3000 字即判失败）
- 提供增量价值：交叉分析/因果解释/影响分析/可执行建议/易忽略问题/有依据的趋势判断
- 避免：无意义小标题、重复总结

【输出格式】
第一行：标题，以 # 开头
第二行起：正文 Markdown（## 表示章节标题，每个核心章节独立）"""

def split_title(article):
    lines = article.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        return lines[0].lstrip().lstrip("#").strip(), "\n".join(lines[1:]).strip()
    return date.today().isoformat(), article

def _inline_md(text):
    """Convert inline markdown (bold, italic, code, links) to HTML."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
    return text

def markdown_to_html(md):
    html_lines = []
    in_list = False
    for line in md.splitlines():
        line = line.rstrip()
        if not line.strip():
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            continue
        # Headings
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            level = len(m.group(1))
            html_lines.append(f"<h{level}>{_inline_md(m.group(2))}</h{level}>")
        # Blockquote
        elif line.strip().startswith(">"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<blockquote>{_inline_md(line.strip()[1:].strip())}</blockquote>")
        # Unordered list
        elif re.match(r"^[-*+]\s+", line):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline_md(line.strip()[2:].strip())}</li>")
        # Ordered list
        elif re.match(r"^\d+\.\s+", line):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{_inline_md(line.strip())}</p>")
        # Horizontal rule
        elif re.match(r"^[-*_]{3,}\s*$", line):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<hr>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{_inline_md(line)}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "".join(html_lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--thumb-url", help="Cover image URL for WeChat thumb")
    args = parser.parse_args()

    with open("output/plan.json", encoding="utf-8") as f:
        plan = json.load(f)
    with open("output/collected.json", encoding="utf-8") as f:
        collected = json.load(f)
    prompt = WRITE_PROMPT.format(
        plan=json.dumps(plan, ensure_ascii=False),
        collected=json.dumps(collected, ensure_ascii=False)[:8000],
    )
    article = llm.chat([{"role": "user", "content": prompt}], temperature=0.8, max_tokens=4096).strip()
    title, body = split_title(article)
    with open(f"output/{date.today()}.md", "w", encoding="utf-8") as f:
        f.write(article)

    articles = {
        "title": title,
        "author": os.environ.get("ARTICLE_AUTHOR", "CorySoft"),
        "digest": os.environ.get("ARTICLE_DIGEST", ""),
        "content": markdown_to_html(body),
    }
    if args.thumb_url:
        articles["thumb_url"] = args.thumb_url
        articles["show_cover_pic"] = 1

    payload = {
        "draft": True,
        "articles": [articles],
    }
    with open("output/article.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"article written: output/{date.today()}.md ; payload: output/article.json")

if __name__ == "__main__":
    main()
