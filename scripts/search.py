import json
import os
import urllib.request
import urllib.parse
from datetime import date

def brave_search(query, api_key, count=10):
    url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={count}"
    req = urllib.request.Request(url, headers={
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [
        {"title": item.get("title"), "url": item.get("url"),
         "description": item.get("description"), "age": item.get("age")}
        for item in data.get("web", {}).get("results", [])
    ]

def free_hn(count=10):
    req = urllib.request.Request(
        "https://hacker-news.firebaseio.com/v0/topstories.json")
    with urllib.request.urlopen(req, timeout=10) as r:
        ids = json.loads(r.read().decode("utf-8"))[:count]
    results = []
    for sid in ids:
        try:
            req = urllib.request.Request(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
            with urllib.request.urlopen(req, timeout=8) as r:
                item = json.loads(r.read().decode("utf-8"))
            if item and item.get("title"):
                results.append({
                    "title": item["title"],
                    "url": item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    "description": item.get("title"),
                    "source": "Hacker News",
                })
        except Exception:
            continue
    return results

def free_reddit(subreddit="artificial", count=10):
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={count}"
    req = urllib.request.Request(url, headers={"User-Agent": "daily-ai-article/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    results = []
    for post in data.get("data", {}).get("children", []):
        d = post.get("data", {})
        if d.get("title"):
            results.append({
                "title": d["title"],
                "url": d.get("url", ""),
                "description": d.get("selftext", "")[:200],
                "source": f"r/{subreddit}",
            })
    return results

def free_arxiv(query="artificial intelligence", count=10):
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}", "start": 0,
        "max_results": count, "sortBy": "submittedDate", "sortOrder": "descending",
    })
    url = f"http://export.arxiv.org/api/query?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as r:
        xml = r.read().decode("utf-8")
    results = []
    import re
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL):
        title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        link = re.search(r'<id>(.*?)</id>', entry)
        if title:
            results.append({
                "title": title.group(1).strip().replace("\n", " "),
                "url": link.group(1).strip() if link else "",
                "description": summary.group(1).strip()[:200].replace("\n", " ") if summary else "",
                "source": "ArXiv",
            })
    return results

def collect_free(queries):
    results = []
    try:
        hn = free_hn(10)
        results.append({"query": "Hacker News Top", "results": hn})
        print(f"  [Hacker News] -> {len(hn)} results")
    except Exception as e:
        print(f"  [Hacker News] 失败: {e}")
    try:
        rd = free_reddit("artificial", 10)
        results.append({"query": "r/artificial", "results": rd})
        print(f"  [Reddit] -> {len(rd)} results")
    except Exception as e:
        print(f"  [Reddit] 失败: {e}")
    try:
        ar = free_arxiv("large language model", 8)
        results.append({"query": "ArXiv LLM", "results": ar})
        print(f"  [ArXiv] -> {len(ar)} results")
    except Exception as e:
        print(f"  [ArXiv] 失败: {e}")
    return results

def main():
    api_key = os.environ.get("SEARCH_API_KEY")
    topics = os.environ.get("SEARCH_TOPICS", "人工智能 最新进展")
    queries = [t.strip() for t in topics.split("|") if t.strip()]
    if not queries:
        raise SystemExit("未提供检索主题 SEARCH_TOPICS")

    all_results = []
    brave_ok = False

    if api_key:
        print("尝试 Brave Search...")
        for q in queries:
            try:
                res = brave_search(q, api_key)
                all_results.append({"query": q, "results": res})
                print(f"  [Brave:{q}] -> {len(res)} results")
                brave_ok = True
            except Exception as e:
                print(f"  [Brave:{q}] 失败: {e}")
    else:
        print("未设置 SEARCH_API_KEY，跳过 Brave")

    if not brave_ok:
        print("Brave 不可用，fallback 到免费源 (HN/Reddit/ArXiv)...")
        all_results = collect_free(queries)

    payload = {
        "date": str(date.today()),
        "topics": queries,
        "sources": all_results,
        "engine": "brave" if brave_ok else "free",
    }
    with open("output/collected.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"collected -> output/collected.json | engine={payload['engine']} | sources={len(all_results)}")

if __name__ == "__main__":
    main()
