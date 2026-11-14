import argparse
import json
import os
import re
import sys
from datetime import date
import llm
from util import slim_collected, word_count as wc
from util import ACCEPT_WORD_MIN, ACCEPT_WORD_MAX, is_complete
from util import recent_outputs, risk_verdict, style_issues
from util import retry_hint

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
- 文中出现的来源 URL 必须就是【策划】里 source_url 那条事件本身（或其原始出处），
  禁止用与本事件无关的链接凑数
- 禁止写成“众所周知/泛泛而谈”的科普：必须围绕选题的新鲜切入点展开，每一章都要推进新信息或新分析，而不是复述常识
- 填充语黑名单（全文合计 ≤2 次）：想象一下、值得注意的是、让我们、综上所述、不难发现、
  可以看到、首先，/其次，/最后， 的三连式

【结构与风格】
- 结构：悬念导语 → 背景 → 核心章节(4~6) → 案例/数据/对比 → 读者影响 → 独立分析 → 有力结尾
- 目标读者：普通大众、科技与 AI 从业者
- 风格：专业、清晰、有观点
- 篇幅：**全文严格控制在 2400~3200 字**（宁少勿多；低于 2200 字或超过 3400 字都判失败）
- 提供增量价值：交叉分析/因果解释/影响分析/可执行建议/易忽略问题/有依据的趋势判断

【排版要求】（重要，必须遵守）
1. 每个核心章节必须用 `##` 小标题分段（小标题要具体、有吸引力，不要空泛；
   禁用「结语」「总结」「展望」「思考」「引言」这类通用名，结尾也要有具体论断）
   - 不要沿用最近几篇的小标题措辞，同一栏目连续出现同套结构即为不合格
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

def _escape_html(text):
    """Escape HTML metacharacters in model output before it enters the draft HTML."""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;"))


def _inline_md(text):
    """Convert inline markdown (bold, italic, code, links) to HTML.
    Model output is untrusted HTML, so escape first, then apply white-listed markdown.
    """
    text = _escape_html(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color:#0F4C81;font-weight:bold;">\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em style="color:#0F4C81;">\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code style="background:#F0F6FA;color:#0F4C81;padding:2px 6px;border-radius:4px;font-size:0.9em;">\1</code>', text)

    def _link(m):
        label, url = m.group(1), m.group(2).strip()
        if url.startswith(("http://", "https://", "#")):
            return f'<a href="{url}" style="color:#0F4C81;text-decoration:underline;">{label}</a>'
        return label

    text = re.sub(r'\[(.+?)\]\((.+?)\)', _link, text)
    return text

_HEADING_STYLE = {
    1: 'background:#0F4C81;color:#fff;border-radius:8px;font-size:22px;display:table;margin:2em auto 1.5em;padding:8px 20px;font-weight:bold;',
    2: 'background:#0F4C81;color:#fff;border-radius:6px;font-size:18px;padding:8px 15px;margin:1.5em 0 1em;font-weight:bold;',
    3: 'font-size:17px;color:#0F4C81;font-weight:bold;margin:18px 0 8px;',
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
                    f'overflow-x:auto;font-size:13px;line-height:1.6;">{_escape_html(code)}</pre>'
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
                f'<img src="IMAGESLOT_PENDING" data-desc="{_escape_html(alt)}" style="width:100%;border-radius:6px;margin:15px 0;display:block;"/>'
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
                f'<p style="margin:0 0 20px;line-height:1.8;color:#3a3a3a;">'
                f'{_inline_md(line)}</p>'
            )

    if in_list:
        html_lines.append("</ul>" if list_type == "ul" else "</ol>")
    if in_blockquote:
        html_lines.append("</blockquote>")
    if in_code:
        code = "\n".join(code_lines)
        html_lines.append(
            f'<pre style="background:#F5F7FA;padding:12px;border-radius:6px;overflow-x:auto;">{_escape_html(code)}</pre>'
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


def _citation_urls(plan, collected):
    """引用只认选题锚点：plan.source_url 已由 S2 按热度档位校验过，确实对应本文事件。

    老逻辑是从 collected 里抓前 3 个 URL 拼成「参考来源」，与选题无关 —— 实测 10 月
    以来 31% 的稿子因此挂着三个毫不相干的域名（讲 YC 掌门人烧 20 万美元，
    末尾链的却是个光盘镜像工具仓库）。锚点缺失时宁可退回到素材里唯一一条，也不再散弹。
    """
    anchor = (plan.get("source_url") or "").strip()
    if anchor.startswith("http"):
        return anchor
    urls = [r.get("url", "") for s in collected.get("sources", []) for r in s.get("results", [])]
    return next((u for u in urls if u.startswith("http")), "")


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

    recent_md, recent_titles = recent_outputs(days=5, kind="daily")
    max_attempts = 3
    article = None
    last_wc = 0
    problems = []
    for attempt in range(max_attempts):
        prompt = base_prompt
        if attempt > 0:
            prompt += ("\n\n【上次生成不合格，请修正】" + retry_hint(
                last_wc,
                "保留所有 ## 小标题、加粗、列表、引用和 2~3 个配图位；"
                "正文中须内嵌至少一条来源 URL。") +
                ("另外：" + "；".join(problems) if problems else ""))
        article = llm.chat([{"role": "user", "content": prompt}], temperature=0.8, max_tokens=8192).strip()
        # Ensure the article contains source URLs; inject from collected data if missing.
        # 必须在验收计数之前注入：否则 S3 量的是注入前、S7 复查的是注入后，
        # 接近上限的文章会被追加的来源行顶出 3400 而整条流水线误判失败。
        if not re.search(r"https?://", article):
            urls = _citation_urls(plan, collected)
            if urls:
                article += f"\n\n> 参考来源：{urls}"
                print(f"Injected source URL: {urls}")
            else:
                print("WARNING: no source URLs found in collected data", file=sys.stderr)
        last_wc = wc(article)
        problems = style_issues(article, recent_md, recent_titles)
        print(f"write attempt {attempt+1}/{max_attempts}: {last_wc} chars"
              + (f" | 排版问题: {'；'.join(problems)}" if problems else ""))
        if ACCEPT_WORD_MIN <= last_wc <= ACCEPT_WORD_MAX and is_complete(article) and not problems:
            break
        if attempt < max_attempts - 1:
            print("  字数越界/疑似截断/排版雷同，重试中...", file=sys.stderr)

    # fail-fast: 字数与截断是硬指标；排版雷同只告警，不值得让整条流水线红
    if not (ACCEPT_WORD_MIN <= last_wc <= ACCEPT_WORD_MAX and is_complete(article)):
        print(
            f"ERROR: 3 attempts, word count {last_wc} outside {ACCEPT_WORD_MIN}~{ACCEPT_WORD_MAX} or truncated, aborting",
            file=sys.stderr,
        )
        sys.exit(1)
    if problems:
        print(f"WARNING: 排版仍雷同，未再重试以免耽误发布: {'；'.join(problems)}", file=sys.stderr)

    title, body = split_title(article)

    # 成稿后自检：日更线是"报道"口径，「攻击/漏洞利用」只告警，其余红线就地停，
    # 免得白烧 S4/S5 的生图再在 S7 红一次
    hard, soft = risk_verdict([plan.get("source_title", ""), plan.get("source_url", "")],
                              [title], False)
    if soft:
        print(f"NOTE: 标题命中 {soft}（安全事件报道口径放行）")
    if hard:
        print(f"ERROR: 成稿命中内容安全红线 {hard}：{title}", file=sys.stderr)
        sys.exit(1)

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