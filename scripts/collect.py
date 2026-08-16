import json
import urllib.request
from datetime import date

def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")

def collect_news():
    url = "https://hn.algolia.com/api/v1/search_by_date?query=&tags=story&hitsPerPage=10"
    data = json.loads(fetch(url))
    items = []
    for hit in data.get("hits", []):
        items.append({
            "title": hit.get("title"),
            "url": hit.get("url"),
            "points": hit.get("points"),
            "comments": hit.get("num_comments"),
            "date": hit.get("created_at"),
        })
    return [i for i in items if i["title"]]

def main():
    news = collect_news()
    payload = {
        "date": str(date.today()),
        "source": "Hacker News",
        "news": news,
    }
    with open("output/collected.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"collected {len(news)} items")

if __name__ == "__main__":
    main()