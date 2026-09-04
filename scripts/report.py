import json
import os
import re
import sys
from datetime import date

from util import word_count


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="", help="File prefix (e.g. 'git_' for git_plan.json)")
    args = parser.parse_args()
    prefix = args.prefix

    md_path = f"output/{prefix}{date.today()}.md"
    plan_path = f"output/{prefix}plan.json"
    article_path = f"output/{prefix}article.json"

    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    with open(article_path, encoding="utf-8") as f:
        article = json.load(f)

    wc = word_count(md)
    title = article["articles"][0]["title"]
    content = article["articles"][0].get("content", "")
    thumb = article["articles"][0].get("thumb_url", "")
    outline = plan.get("outline", [])
    sections = [l for l in md.splitlines() if l.lstrip().startswith("## ")]
    image_slots = len(re.findall(r'^!\[[^\]]*\]$', md, re.MULTILINE))
    has_source = bool(re.search(r"https?://", md))
    if not has_source:
        has_source = bool(re.search(r"https?://", content))
    has_pending = "IMAGESLOT_PENDING" in content
    thumb_ok = bool(thumb) and "$IMG_COMMIT" not in thumb

    checks = [
        ("字数 1800~3000", 1800 <= wc <= 3000),
        ("有标题", bool(title)),
        ("章节 >= 3", len(sections) >= 3),
        ("正文含来源 URL", has_source),
        ("配图位 >= 1", image_slots >= 1),
        ("文章 JSON 生成", os.path.exists(article_path)),
        ("正文 Markdown 生成", os.path.exists(md_path)),
        ("配图槽已填充", not has_pending),
        ("封面 thumb_url 有效", thumb_ok),
    ]

    print("=" * 40)
    print(f"标题: {title}")
    print(f"字数: {wc}")
    print(f"章节数: {len(sections)}")
    print(f"策划章节: {len(outline)}")
    print(f"配图位: {image_slots}")
    print("-" * 40)
    for name, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")

    report = {
        "date": str(date.today()),
        "title": title,
        "word_count": wc,
        "sections": sections,
        "core_view": plan.get("core_view"),
        "checks": {name: ok for name, ok in checks},
        "all_pass": all(ok for _, ok in checks),
    }
    with open(f"output/{prefix}report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nreport: output/{prefix}report.json  all_pass={report['all_pass']}")

    if not report["all_pass"]:
        print("ERROR: verification failed, aborting pipeline", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
