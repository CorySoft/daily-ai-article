import json
import os
import sys
import urllib.request
from datetime import date

def brave_search(query, api_key, count=10):
    url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={count}"
    req = urllib.request.Request(url, headers={
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [
        {"title": item.get("title"), "url": item.get("url"),
         "description": item.get("description"), "age": item.get("age")}
        for item in data.get("web", {}).get("results", [])
    ]

def main():
    api_key = os.environ.get("SEARCH_API_KEY")
    if not api_key:
        raise SystemExit("缺少 SEARCH_API_KEY 环境变量")
    topics = os.environ.get("SEARCH_TOPICS", "人工智能 最新进展")
    queries = [t.strip() for t in topics.split("|") if t.strip()]
    if not queries:
        raise SystemExit("未提供检索主题 SEARCH_TOPICS")

    all_results = []
    for q in queries:
        try:
            res = brave_search(q, api_key)
            all_results.append({"query": q, "results": res})
            print(f"  [{q}] -> {len(res)} results")
        except Exception as e:
            print(f"  [{q}] 失败: {e}")  # 单链接失败跳过（异常处理矩阵）

    payload = {
        "date": str(date.today()),
        "topics": queries,
        "sources": all_results,
    }
    with open("output/collected.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"collected into output/collected.json, total queries: {len(all_results)}")

if __name__ == "__main__":
    import urllib.parse
    main()
