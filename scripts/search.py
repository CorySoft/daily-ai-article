import json
import os
import re
import urllib.request
import urllib.parse
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

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

def _get(url, timeout=15):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if HAS_HTTPX:
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            r = client.get(url, headers=headers)
            return r.text
    else:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")

def extract_content_from_html(html, source_name=""):
    if not HAS_BS4: return ""
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "nav", "footer", "aside", "header"]):
        s.decompose()
    article = soup.find("article")
    if article:
        text = article.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) > 15]
    return "\n".join(lines[:50])

def free_hn(count=10):
    req = urllib.request.Request("https://hacker-news.firebaseio.com/v0/topstories.json")
    with urllib.request.urlopen(req, timeout=10) as r:
        ids = json.loads(r.read().decode("utf-8"))[:count]
    results = []
    now = int(datetime.now(timezone.utc).timestamp())
    for sid in ids:
        try:
            req = urllib.request.Request(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
            with urllib.request.urlopen(req, timeout=8) as r:
                item = json.loads(r.read().decode("utf-8"))
            if item and item.get("title"):
                ts = item.get("time") or 0
                results.append({
                    "title": item["title"],
                    "url": item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    "description": item.get("title"),
                    "source": "Hacker News",
                    "age_hours": round((now - ts) / 3600, 1) if ts else None,
                    "hotness": item.get("score") or 0,
                    "pub_date": datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else "",
                })
        except Exception:
            continue
    return results

def free_techcrunch(count=10):
    results = []
    try:
        html = _get("https://techcrunch.com/feed/")
        if HAS_BS4:
            soup = BeautifulSoup(html, "xml")
            items = soup.find_all("item")[:count]
            for item in items:
                title = item.title.get_text(strip=True)
                link = item.link.get_text(strip=True)
                desc = item.find("description")
                desc_text = desc.get_text(strip=True)[:200] if desc else ""
                pub = item.find("pubDate")
                pub_text = pub.get_text(strip=True) if pub else ""
                pub_iso = ""
                if pub_text:
                    try:
                        pub_iso = parsedate_to_datetime(pub_text).date().isoformat()
                    except Exception:
                        pub_iso = pub_text[:16]
                if title:
                    results.append({
                        "title": title, "url": link,
                        "description": f"TechCrunch: {desc_text}",
                        "source": "TechCrunch",
                        "pub_date": pub_iso,
                    })
    except Exception as e:
        print(f"  [TechCrunch] 失败: {e}")
    return results

def free_arxiv(query="artificial intelligence", count=10):
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}", "start": 0,
        "max_results": count, "sortBy": "submittedDate", "sortOrder": "descending",
    })
    url = f"https://export.arxiv.org/api/query?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as r:
        xml = r.read().decode("utf-8")
    results = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL):
        title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
        link = re.search(r'<id>(.*?)</id>', entry)
        pub = re.search(r"<published>(.*?)</published>", entry)
        if title:
            results.append({
                "title": title.group(1).strip().replace("\n", " "),
                "url": link.group(1).strip() if link else "",
                "description": summary.group(1).strip()[:200].replace("\n", " ") if summary else "",
                "source": "ArXiv",
                "pub_date": pub.group(1)[:10] if pub else "",
            })
    return results

def free_github_trending(count=10):
    """Scrape GitHub trending for today's hottest repos (no auth needed)."""
    results = []
    try:
        html = _get("https://github.com/trending?since=daily")
        if HAS_BS4:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.select("article.Box-row")[:count]
            for a in articles:
                h = a.select_one("h2 a")
                if not h:
                    continue
                name = h.get_text(strip=True).replace("\n", "")
                lang_el = a.select_one("[itemprop='programmingLanguage']")
                desc_el = a.select_one("p")
                stars_el = a.select_one("a[href$='/stargazers']")
                desc = desc_el.get_text(strip=True) if desc_el else ""
                stars = re.search(r"([\d,]+)", stars_el.get_text(strip=True)) if stars_el else None
                results.append({
                    "title": f"{name} 在 GitHub 上今日热度上升",
                    "url": f"https://github.com/{name}",
                    "description": (desc or f"{name} 今日登上 GitHub Trending"),
                    "source": "GitHub Trending",
                    "language": lang_el.get_text(strip=True) if lang_el else "",
                    "github_full_name": name,
                    "stars_text": stars.group(1) if stars else "",
                })
    except Exception as e:
        print(f"  [GitHub Trending] 失败: {e}")
    return results


def rank_by_freshness(sources, now=None):
    """Compute recency score per item and reorder results so the newest/hottest lead.
    Returns (sources, stats) where stats exposes per-source freshness for the plan step.
    """
    import math
    now = now or datetime.now(timezone.utc)
    stats = []
    for src in sources:
        items = src.get("results", [])
        for it in items:
            score = 1.0
            # Recency: HN age_hours / pub_date recency decay
            ah = it.get("age_hours")
            if ah is not None and ah >= 0:
                # <24h: near-full; 24-72h: 0.7; >72h: decays fast
                score *= max(0.1, 1.0 / (1.0 + math.log10(1 + ah)))
            else:
                pd = it.get("pub_date", "")
                if pd:
                    try:
                        d = datetime.fromisoformat(pd[:10].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                        days = (now - d).days
                        score *= max(0.1, 1.0 / (1.0 + max(0, days) * 0.4))
                    except Exception:
                        try:  # RFC822 like "Mon, 12 Oct 2026"
                            d = parsedate_to_datetime(pd)
                            if d.tzinfo is None:
                                d = d.replace(tzinfo=timezone.utc)
                            days = (now - d).days
                            score *= max(0.1, 1.0 / (1.0 + max(0, days) * 0.4))
                        except Exception:
                            pass
            hot = it.get("hotness") or 0
            score *= 1.0 + math.log1p(hot) / 10.0  # HN score boost (up to ~ +60%)
            it["recency"] = round(score, 3)
        items.sort(key=lambda x: (x.get("recency") or 0), reverse=True)
        top = items[0]["recency"] if items else 0
        stats.append({"query": src.get("query"), "source_count": len(items), "max_recency": top})
    return sources, stats


def collect_full_texts(results, per_source=4):
    print("开始正文精读...")
    for source in results:
        for item in source.get("results", [])[:per_source]:
            if item.get("full_text") or not item.get("url"):
                continue
            if "mmbiz.qpic.cn" in item.get("url") or "github.com" in item.get("url"):
                continue
            try:
                html = _get(item["url"], timeout=12)
                full_text = extract_content_from_html(html, source.get("query", ""))
                if full_text and len(full_text) > 100:
                    item["full_text"] = full_text[:2000]
                    print(f"  [精读] {item['title'][:10]}... ({len(full_text)} 字)")
            except Exception as e:
                print(f"  [精读失败] {item['title'][:10]}... {e}")
                continue

def _arxiv_query(query):
    """arXiv 索引是英文的；从 SEARCH_TOPICS 推导英文字段，中文则回退到热门组合。"""
    latin = re.findall(r"[A-Za-z][A-Za-z0-9+.\- ]*", query)
    if any(len(t) > 3 for t in latin):
        return query
    zh_map = {
        "人工智能": "artificial intelligence",
        "大模型": "large language model",
        "大语言模型": "large language model",
        "模型": "language model",
        "机器学习": "machine learning",
        "深度学习": "deep learning",
        "多模态": "multimodal",
        "推理": "reasoning",
        "智能体": "agent",
        "机器人": "robot",
        "检索": "retrieval",
        "扩散": "diffusion",
    }
    for zh, en in zh_map.items():
        if zh in query:
            return en
    return "artificial intelligence"


def collect_free(queries):
    results = []
    try:
        hn = free_hn(10)
        results.append({"query": "Hacker News Top", "results": hn})
        print(f"  [Hacker News] -> {len(hn)} results")
    except Exception as e:
        print(f"  [Hacker News] 失败: {e}")
    try:
        kr = free_techcrunch(10)
        results.append({"query": "TechCrunch Latest", "results": kr})
        print(f"  [TechCrunch] -> {len(kr)} results")
    except Exception as e:
        print(f"  [TechCrunch] 失败: {e}")
    try:
        gt = free_github_trending(8)
        results.append({"query": "GitHub Trending Today", "results": gt})
        print(f"  [GitHub Trending] -> {len(gt)} results")
    except Exception as e:
        print(f"  [GitHub Trending] 失败: {e}")
    for q in queries[:2]:
        try:
            ar = free_arxiv(_arxiv_query(q), 8)
            results.append({"query": f"ArXiv: {_arxiv_query(q)}", "results": ar})
            print(f"  [ArXiv:{_arxiv_query(q)}] -> {len(ar)} results")
        except Exception as e:
            print(f"  [ArXiv:{q}] 失败: {e}")
    results, stats = rank_by_freshness(results)
    return results, stats

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
        print("Brave 不可用，fallback 到免费源 (HN/TechCrunch/GitHub Trending/ArXiv)...")
        all_results, freshness = collect_free(queries)
    else:
        print("Brave 成功，补充免费源...")
        try:
            extra, freshness = collect_free(queries)
            all_results.extend(extra)
        except Exception as e:
            print(f"  免费源补充失败: {e}")
            freshness = []

    collect_full_texts(all_results)

    payload = {
        "date": str(date.today()),
        "topics": queries,
        "sources": all_results,
        "freshness": freshness,
        "engine": "brave" if brave_ok else "free",
    }
    os.makedirs("output", exist_ok=True)
    with open("output/collected.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"collected -> output/collected.json | engine={payload['engine']} | sources={len(all_results)}")

if __name__ == "__main__":
    main()
