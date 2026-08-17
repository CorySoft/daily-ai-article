import json
import os
import re
from datetime import date

def word_count(md):
    body = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith("#"))
    return len(re.sub(r"\s", "", body))

def main():
    md_path = f"output/{date.today()}.md"
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    with open("output/plan.json", encoding="utf-8") as f:
        plan = json.load(f)
    with open("output/article.json", encoding="utf-8") as f:
        article = json.load(f)

    wc = word_count(md)
    title = article["articles"][0]["title"]
    outline = plan.get("outline", [])
    sections = [l for l in md.splitlines() if l.lstrip().startswith("## ")]
    has_facts = bool(plan.get("facts"))

    checks = [
        ("字数 1800~3000", 1800 <= wc <= 3000),
        ("有标题", bool(title)),
        ("章节 >= 3", len(sections) >= 3),
        ("包含事实标注", has_facts),
        ("文章 JSON 生成", os.path.exists("output/article.json")),
        ("正文 Markdown 生成", os.path.exists(md_path)),
    ]

    print("=" * 40)
    print(f"标题: {title}")
    print(f"字数: {wc}")
    print(f"章节数: {len(sections)}")
    print(f"策划章节: {len(outline)}")
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
    with open("output/report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nreport: output/report.json  all_pass={report['all_pass']}")

if __name__ == "__main__":
    main()
