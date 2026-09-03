import json
import re


def word_count(md):
    body = "\n".join(l for l in md.splitlines() if not l.lstrip().startswith("#"))
    return len(re.sub(r"\s", "", body))


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
