"""S1: Search GitHub for a valuable open-source project to feature.
Uses GitHub REST API (authenticated via GITHUB_TOKEN or anonymous).
Outputs output/git_collected.json with project info.
"""
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

GITHUB_API = "https://api.github.com"

def _gh_get(path, token=None):
    """GET request to GitHub API."""
    url = f"{GITHUB_API}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "daily-ai-article/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def search_repos(token=None):
    """Search for high-quality repos: recent activity, good stars, has README."""
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc)
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    day_3_ago = (today - timedelta(days=3)).strftime("%Y-%m-%d")

    queries = [
        f"stars:>30 pushed:>{week_ago}",
        f"stars:>50 pushed:>{week_ago} language:Python",
        f"stars:>40 pushed:>{week_ago} language:JavaScript",
        f"stars:>40 pushed:>{week_ago} language:Go",
        f"stars:>40 pushed:>{week_ago} language:Rust",
        f"stars:>30 created:>{day_3_ago}",
    ]

    all_repos = []
    for q in queries:
        try:
            quoted = urllib.parse.quote(q, safe=":>,-")
            data = _gh_get(f"/search/repositories?q={quoted}&sort=stars&order=desc&per_page=10", token)
            items = data.get("items", [])
            all_repos.extend(items)
            print(f"  [GitHub] query '{q[:40]}...' -> {len(items)} results")
            time.sleep(1)  # rate limit courtesy
        except Exception as e:
            print(f"  [GitHub] query failed: {e}")
            continue

    # Deduplicate by id
    seen = set()
    unique = []
    for r in all_repos:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)

    # Filter: must have description, be open source, not too small
    filtered = []
    for r in unique:
        desc = r.get("description", "")
        license_ = r.get("license", {})
        topics = r.get("topics", [])
        # Skip if: no description, or archived, or fork with low stars
        if not desc or r.get("archived"):
            continue
        # Skip repos that look like tutorials/courses/books
        skip_keywords = ["tutorial", "course", "awesome-", "free-programming", "interview", "roadmap"]
        name_lower = r["full_name"].lower()
        desc_lower = desc.lower()
        if any(kw in name_lower or kw in desc_lower for kw in skip_keywords):
            continue
        # Prefer repos with good stars and recent activity
        stars = r.get("stargazers_count", 0)
        pushed = r.get("pushed_at", "")
        filtered.append({
            "id": r["id"],
            "full_name": r["full_name"],
            "name": r["name"],
            "description": desc,
            "url": r["html_url"],
            "stars": stars,
            "forks": r.get("forks_count", 0),
            "language": r.get("language"),
            "topics": topics[:5],
            "license": license_.get("spdx_id") if license_ else None,
            "created_at": r.get("created_at", ""),
            "pushed_at": pushed,
            "homepage": r.get("homepage", ""),
        })

    print(f"  [GitHub] total unique filtered: {len(filtered)} repos")
    return filtered

def main():
    from datetime import date
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    print(f"GitHub API auth: {'token' if token else 'anonymous (60 req/hr)'}")

    repos = search_repos(token)
    if not repos:
        print("ERROR: No repos found", file=sys.stderr)
        sys.exit(1)

    # Pick a random high-quality repo (weighted by stars)
    # Use top 50% by stars and pick randomly for variety
    repos.sort(key=lambda r: r["stars"], reverse=True)
    top_half = repos[:max(len(repos) // 2, 1)]
    chosen = random.choice(top_half)

    output = {
        "date": date.today().isoformat(),
        "engine": "github_api",
        "total_candidates": len(repos),
        "selected": chosen,
        "alternatives": [r["full_name"] for r in repos if r["id"] != chosen["id"]][:5],
    }

    os.makedirs("output", exist_ok=True)
    with open("output/git_collected.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"selected: {chosen['full_name']} ({chosen['stars']}⭐) - {chosen['description'][:60]}")
    print(f"output: output/git_collected.json")

if __name__ == "__main__":
    main()
