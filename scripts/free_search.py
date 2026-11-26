"""S1: Collect currently-available *official* free-tier offers.

Only links on a vendor's own domain are accepted, and every candidate passes
util.risk_flags plus an extra grey-pattern filter. This column reports official
free quotas -- it never teaches batch registration / SMS-code farming / account
sharing, which the project's content red lines forbid.

Reads env SEARCH_API_KEY (Brave, optional) and FREE_SEARCH_TOPICS / SEARCH_TOPICS.
Outputs output/free_collected.json.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

import search as websearch
from util import risk_flags

# 只认厂商自己的域名：转载/聚合/"免费领取"落地页一律不进候选
OFFICIAL_HOSTS = (
    "openai.com", "anthropic.com", "google.com", "deepmind.google",
    "microsoft.com", "azure.microsoft.com", "github.com", "huggingface.co",
    "groq.com", "together.ai", "fireworks.ai", "cohere.com", "mistral.ai",
    "deepseek.com", "moonshot.cn", "bigmodel.cn", "qwen.ai", "alibabacloud.com",
    "aliyun.com", "cloud.google.com", "aws.amazon.com", "oracle.com",
    "cloudflare.com", "vercel.com", "netlify.com", "render.com", "fly.io",
    "railway.app", "supabase.com", "neon.tech", "planetscale.com",
    "mongodb.com", "redis.io", "convex.dev", "replit.com", "glitch.com",
    "ngrok.com", "zeromq.org", "hetzner.com", "ovhcloud.com", "contabo.com",
    "digitalocean.com", "linode.com", "scaleway.com", "oraclecloud.com",
    "twilio.com", "syniverse.com", "telnyx.com", "plivo.com", "sinch.com",
    "botpress.com", "flowiseai.com", "n8n.io", "make.com", "zapier.com",
)

# 免费层的语义信号：没有它就只是普通产品页，不是「羊毛」线索
FREE_SIGNAL = re.compile(r"free|免费|gratis|0\s*元|不花钱|credits?|trial", re.IGNORECASE)
# 现有 RISK_PATTERNS 之外的灰产变体：这一栏只报官方额度，不教绕过手段
GREY_PATTERNS = re.compile(
    r"羊毛党?|接码|养号|批量注册|卡商|免税卡|代挂|刷单|共享账号|合租账号|拼车账号|"
    r"免费领(?:取)?(?:会员|账号)|试用号交易|trial[-\s]?abuse|"
    r"free[-\s]?trial[-\s]?(?:script|auto|bot)",
    re.IGNORECASE,
)

MAX_AGE_DAYS = 30
MIN_CANDIDATES = 3
MAX_CANDIDATES = 20
FEATURED_PATH = "output/free_featured.json"

CATEGORIES = [
    ("token", "free API credits official free tier LLM tokens"),
    ("agent", "official free AI agent plan free tier assistant"),
    ("cloud", "official free cloud tier free credits sign up"),
    ("vps", "official free VPS free tier virtual machine always free"),
    ("phone", "official free virtual phone number trial developer"),
]


def normalize_url(url):
    """稳定去重键：忽略 scheme / 末尾斜杠 / 常见跟踪参数，保留域名与路径。"""
    if not url:
        return ""
    p = urllib.parse.urlparse(url.strip())
    host = (p.hostname or "").lower()
    path = re.sub(r"/+$", "", p.path.lower())
    return f"{host}{path}"


def is_official(url):
    host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_HOSTS)


def _days_old(item):
    pd = str(item.get("pub_date") or "")[:10]
    if pd:
        try:
            return (date.today() - date.fromisoformat(pd)).days
        except ValueError:
            pass
    age = item.get("age_hours")
    if isinstance(age, (int, float)):
        return age / 24
    return None


def gate(item):
    """单条免费额度候选的硬门槛。纯函数，离线可测。"""
    url = str(item.get("url") or "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return False, "非 HTTPS 官方链接"
    if not is_official(url):
        return False, "非官方域名"
    if (parsed.hostname or "").lower() == "github.com" and len([p for p in parsed.path.split("/") if p]) > 1:
        return False, "GitHub 仓库页不是官方条款页"
    if not str(item.get("title") or "").strip():
        return False, "无标题"
    text = " ".join(str(item.get(k) or "") for k in ("title", "description", "url"))
    if not FREE_SIGNAL.search(text):
        return False, "无免费层信号"
    risky = risk_flags(text)
    if risky:
        return False, "risk " + "/".join(risky)
    if GREY_PATTERNS.search(text):
        return False, "灰产手法"
    days = _days_old(item)
    if days is not None and days > MAX_AGE_DAYS:
        return False, f"过期（{days:.0f}天）"
    return True, ""


def load_featured():
    if not os.path.exists(FEATURED_PATH):
        return set()
    with open(FEATURED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {normalize_url(item.get("url")) for item in data if item.get("url")}


def mark_featured(url):
    """写过的额度记一笔，避免明天同一家再上一次。"""
    key = normalize_url(url)
    if not key:
        return
    items = []
    if os.path.exists(FEATURED_PATH):
        with open(FEATURED_PATH, encoding="utf-8") as f:
            items = json.load(f)
    if all(normalize_url(i.get("url")) != key for i in items):
        items.append({"url": url, "date": date.today().isoformat()})
        with open(FEATURED_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)


def _hn(query, count=8):
    """HN Algolia，免密钥；热度分用作排序信号。"""
    url = "https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode({
        "query": query, "tags": "story", "hitsPerPage": count,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 DailyAI/1.0"})
    results = []
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    for hit in data.get("hits", []):
        if not hit.get("url"):
            continue
        created = hit.get("created_at") or ""
        results.append({
            "title": hit.get("title") or "",
            "url": hit["url"],
            "description": hit.get("story_text") or hit.get("title") or "",
            "source": "Hacker News",
            "hotness": hit.get("points") or 0,
            "pub_date": created[:10],
            "age_hours": None,
        })
    return results


def _brave(query, api_key, count=10):
    results = []
    for item in websearch.brave_search(query, api_key, count=count):
        if not item.get("url"):
            continue
        age = str(item.get("age") or "")
        m = re.search(r"(\d+)\s*(hour|day|week|month|year)s?\s*ago", age, re.IGNORECASE)
        age_hours = None
        if m:
            n, unit = int(m.group(1)), m.group(2).lower()
            factor = {"hour": 1, "day": 24, "week": 168, "month": 720, "year": 8760}[unit]
            age_hours = n * factor
        results.append({
            "title": item.get("title") or "",
            "url": item["url"],
            "description": item.get("description") or "",
            "source": "Brave",
            "hotness": 0,
            "age_hours": age_hours,
            "pub_date": (date.today() - timedelta(days=int(age_hours / 24))).isoformat() if age_hours else "",
        })
    return results


def collect(api_key=None):
    topics = [t.strip() for t in os.environ.get("FREE_SEARCH_TOPICS", "").split("|") if t.strip()]
    if not topics:
        topics = [t.strip() for t in os.environ.get("SEARCH_TOPICS", "").split("|") if t.strip()]
    queries = [(cat, q) for cat, q in CATEGORIES]
    queries += [("custom", t) for t in topics[:5]]

    sources, seen = [], set()
    for category, query in queries:
        found = []
        if api_key:
            try:
                found += _brave(query, api_key)
            except Exception as e:
                print(f"  [Brave] '{query[:30]}' failed: {e}")
        try:
            found += _hn(query)
        except Exception as e:
            print(f"  [HN] '{query[:30]}' failed: {e}")

        kept = []
        for item in found:
            key = normalize_url(item.get("url"))
            if not key or key in seen:
                continue
            seen.add(key)
            ok, reason = gate(item)
            if not ok:
                if reason.startswith("risk") or "灰产" in reason:
                    print(f"  [skip] {key}: {reason}")
                continue
            item["category"] = category
            kept.append(item)
        print(f"  [{category}] {len(kept)}/{len(found)} official free-tier candidates")
        if kept:
            sources.append({"query": query, "category": category, "results": kept})
    return sources


def main():
    api_key = os.environ.get("SEARCH_API_KEY")
    os.makedirs("output", exist_ok=True)
    print(f"Brave API: {'on' if api_key else 'off (HN only)'}")
    sources = collect(api_key)
    featured = load_featured()
    items = [it for s in sources for it in s["results"] if normalize_url(it.get("url")) not in featured]
    items.sort(key=lambda x: (x.get("hotness") or 0,
                              -(_days_old(x) if _days_old(x) is not None else 999)),
               reverse=True)
    items = items[:MAX_CANDIDATES]
    if len(items) < MIN_CANDIDATES:
        print(f"ERROR: 只剩 {len(items)} 条通过官方域名/风险/时效门槛的候选（需 ≥{MIN_CANDIDATES}）",
              file=sys.stderr)
        sys.exit(1)

    output = {
        "date": date.today().isoformat(),
        "engine": "brave+hn",
        "already_featured": len(featured),
        "sources": [{"query": s["query"], "category": s["category"], "results": s["results"]}
                    for s in sources],
    }
    with open("output/free_collected.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"selected pool: {len(items)} offers -> output/free_collected.json")
    for it in items[:5]:
        print(f"  {it['category']:6s} {it['title'][:60]} | {normalize_url(it['url'])}")


if __name__ == "__main__":
    main()
