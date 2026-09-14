import json
import re


# 全文验收阈值：write.py / git_write.py / report.py 共用，避免口径漂移
ACCEPT_WORD_MIN = 1800
ACCEPT_WORD_MAX = 3400
TARGET_WORD_MIN = 2400
TARGET_WORD_MAX = 3200


def word_count(md):
    body = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith("#"))
    return len(re.sub(r"\s", "", body))


_TRAILING_PUNCT = ("。", "！", "？", "。”", "！”", "？”", "》", "）", ".")


def is_complete(text):
    """True if the article was not truncated by max_tokens.
    A complete essay ends with sentence punctuation and has >=3 ## sections.
    A trailing URL line (typical for 【开源精选】: "🔗 GitHub: https://...")
    is stripped before checking, so the closing sentence decides completeness.
    """
    lines = text.rstrip().splitlines()
    while lines:
        last = lines[-1]
        if re.search(r'https?://\S+', last) and re.search(r'(🔗|\bGitHub\b)', last):
            lines.pop()
            continue
        break
    t = "\n".join(lines).rstrip()
    ends_ok = t.endswith(_TRAILING_PUNCT)
    has_sections = len(re.findall(r"^## ", text, re.MULTILINE)) >= 3
    return bool(ends_ok) and has_sections


def slim_collected(collected, max_chars=8000, max_items=6, excerpt_len=400):
    sources = []
    for source in collected.get("sources", []):
        items = []
        for item in source.get("results", [])[:max_items]:
            entry = {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "description": (item.get("description") or "")[:240],
            }
            ft = item.get("full_text") or ""
            if ft:
                entry["excerpt"] = ft[:excerpt_len]
            items.append(entry)
        sources.append({"query": source.get("query"), "results": items})
    payload = {
        "date": collected.get("date"),
        "topics": collected.get("topics"),
        "engine": collected.get("engine"),
        "sources": sources,
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    for source in sources:
        for item in source["results"]:
            item.pop("excerpt", None)
    payload["sources"] = sources
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    while sources and len(text) > max_chars:
        if sources[-1]["results"]:
            sources[-1]["results"].pop()
            if not sources[-1]["results"]:
                sources.pop()
        else:
            sources.pop()
        payload["sources"] = sources
        text = json.dumps(payload, ensure_ascii=False)
    return text
