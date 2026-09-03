import argparse
import json
import os
import re
import sys
from datetime import date
import llm
from util import slim_collected, word_count as wc

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
- 结构：悬念导语 → 背景 → 核心章节(4~6) → 案例/数据/对比 → 读者影响 → 独立分析 → 有力结尾
- 目标读者：普通大众、科技与 AI 从业者
- 风格：专业、清晰、有观点
- 篇幅：**全文严格控制在 2400~3000 字**（宁少勿多，超过 3200 字即判失败）
- 提供增量价值：交叉分析/因果解释/影响分析/可执行建议/易忽略问题/有依据的趋势判断

【排版要求】（重要，必须遵守）
1. 每个核心章节必须用 `##` 小标题分段（小标题要具体、有吸引力，不要空泛）
2. 正文多用排版标记：**加粗**关键观点、>引用数据或言论、- 列要点（每章至少一个列表或引用）
3. 在合适的章节标注 2~3 张配图位置，格式：`![配图描述：一句话说明画面内容]`
    - 描述必须是可绘制的物体/场景/材质/光影，不要写截图、界面、仓库页、徽章、按钮、流程图、带字屏幕
    - 不要出现文字、数字、Logo；用隐喻表达观点（例如「过热的核心被冷却管道环绕」）
    - 放在正文段落之间的独立一行
4. 标题第一行用 `#`，其后空一行接正文

【输出格式】
第一行：标题，以 # 开头
第二行起：正文 Markdown"""

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
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" style="color:#0F4C81;text-decoration:underline;">\1</a>', text)
    return text

_HEADING_STYLE = {
    1: 'font-size:24px;color:#0F1322;font-weight:bold;margin:10px 0;padding:12px 16px;background:linear-gradient(90deg,#0F4C81,#55C9EA);color:#fff;border-radius:6px;',
    2: 'font-size:20px;color:#0F4C81;font-weight:bold;margin:24px 0 12px;padding-left:12px;border-left:4px solid #55C9EA;',
    3: 'font-size:17px;color:#0F1322;font-weight:bold;margin:18px 0 8px;',
}

def markdown_to_html(md):
    """Convert markdown to WeChat-friendly HTML with inline styles."""
    html_lines = []
    in_list = False
    list_type = None
    in_code = False
    code_lines = []
    in_blockquote = False

    for line in md.splitlines():
        line = line.rstrip()

        # Code block fence
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                code_lines = []
            else:
                in_code = False
                code = "\n".join(code_lines)
                html_lines.append(
                    f'<pre style="background:#F5F7FA;padding:12px;border-radius:6px;'
                    f'overflow-x:auto;font-size:13px;line-height:1.6;">{code}</pre>'
                )
            continue
        if in_code:
            code_lines.append(line)
            continue

        # Image slot: ![配图描述：...]
        m = re.match(r'^!\[([^\]]*)\]$', line.strip())
        if m:
            alt = m.group(1).replace("配图描述：", "").strip()
            html_lines.append(
                f'<figure style="margin:20px 0;text-align:center;">'
                f'<img src="IMAGESLOT_PENDING" data-desc="{alt}" style="width:100%;border-radius:8px;"/>'
                f'</figure>'
            )
            continue

        # Close list when leaving list context
        if (in_list and not re.match(r'^[-*+]\s+', line) and not re.match(r'^\d+\.\s+', line)):
            html_lines.append("</ul>" if list_type == "ul" else "</ol>")
            in_list = False

        # Blank line
        if not line.strip():
            if in_blockquote:
                html_lines.append("</blockquote>")
                in_blockquote = False
            continue

        # Headings
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            if in_blockquote:
                html_lines.append("</blockquote>")
                in_blockquote = False
            level = len(m.group(1))
            style = _HEADING_STYLE.get(level, _HEADING_STYLE[3])
            html_lines.append(f"<h{level} style=\"{style}\">{_inline_md(m.group(2))}</h{level}>")
        # Blockquote
        elif line.strip().startswith(">"):
            if not in_blockquote:
                html_lines.append(
                    '<blockquote style="margin:16px 0;padding:12px 16px;background:#F0F6FA;'
                    'border-left:4px solid #55C9EA;color:#45536B;font-style:italic;border-radius:4px;">'
                )
                in_blockquote = True
            html_lines.append(_inline_md(line.strip()[1:].strip()))
        # Unordered list
        elif re.match(r"^[-*+]\s+", line):
            if in_list and list_type != "ul":
                html_lines.append("</ol>")
                in_list = False
            if not in_list:
                html_lines.append('<ul style="margin:12px 0;padding-left:20px;">')
                in_list = True
                list_type = "ul"
            html_lines.append(f'<li style="margin:6px 0;line-height:1.7;">{_inline_md(line.strip()[2:].strip())}</li>')
        # Ordered list
        elif re.match(r"^\d+\.\s+", line):
            if in_list and list_type != "ol":
                html_lines.append("</ul>")
                in_list = False
            if not in_list:
                html_lines.append('<ol style="margin:12px 0;padding-left:20px;">')
                in_list = True
                list_type = "ol"
            item_text = re.sub(r'^\d+\.\s+', '', line.strip())
            html_lines.append(f'<li style="margin:6px 0;line-height:1.7;">{_inline_md(item_text)}</li>')
        # Horizontal rule
        elif re.match(r"^[-*_]{3,}\s*$", line):
            html_lines.append('<hr style="border:none;border-top:1px solid #E5E7EB;margin:20px 0;">')
        # Paragraph
        else:
            html_lines.append(
                f'<p style="margin:12px 0;line-height:1.9;font-size:16px;color:#333;text-align:justify;">'
                f'{_inline_md(line)}</p>'
            )

    if in_list:
        html_lines.append("</ul>" if list_type == "ul" else "</ol>")
    if in_blockquote:
        html_lines.append("</blockquote>")
    if in_code:
        code = "\n".join(code_lines)
        html_lines.append(
            f'<pre style="background:#F5F7FA;padding:12px;border-radius:6px;overflow-x:auto;">{code}</pre>'
        )
    return "".join(html_lines)


def extract_image_slots(md):
    """Extract image descriptions from markdown image slots.
    Returns list of {"desc": str}."""
    slots = []
    for line in md.splitlines():
        m = re.match(r'^!\[([^\]]*)\]$', line.strip())
        if m:
            desc = m.group(1).replace("配图描述：", "").strip()
            slots.append({"desc": desc})
    return slots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--thumb-url", help="Cover image URL for WeChat thumb")
    args = parser.parse_args()

    with open("output/plan.json", encoding="utf-8") as f:
        plan = json.load(f)
    with open("output/collected.json", encoding="utf-8") as f:
        collected = json.load(f)
    base_prompt = WRITE_PROMPT.format(
        plan=json.dumps(plan, ensure_ascii=False),
        collected=slim_collected(collected),
    )

    max_attempts = 3
    article = None
    last_wc = 0
    for attempt in range(max_attempts):
        prompt = base_prompt
        if attempt > 0:
            prompt += f"\n\n【上次生成不合格，请修正】上次全文为 {last_wc} 字（含标题行）。必须把正文压缩到 2400~3000 字，删除冗余段落，保留所有 ## 小标题、加粗、列表、引用和 2~3 个配图位。"
        article = llm.chat([{"role": "user", "content": prompt}], temperature=0.8, max_tokens=4096).strip()
        last_wc = wc(article)
        print(f"write attempt {attempt+1}/{max_attempts}: {last_wc} chars")
        if 1800 <= last_wc <= 3000:
            break
        if attempt < max_attempts - 1:
            print(f"  word count {last_wc} out of range, retrying...", file=sys.stderr)

    title, body = split_title(article)
    with open(f"output/{date.today()}.md", "w", encoding="utf-8") as f:
        f.write(article)

    # Save image slot metadata for later generation
    image_slots = extract_image_slots(body)
    with open("output/images_meta.json", "w", encoding="utf-8") as f:
        json.dump(image_slots, f, ensure_ascii=False, indent=2)

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
    print(f"article written: output/{date.today()}.md ; payload: output/article.json ; images: {len(image_slots)}")


if __name__ == "__main__":
    main()