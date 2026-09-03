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

import github_api

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
            data = github_api.get(f"/search/repositories?q={quoted}&sort=stars&order=desc&per_page=10", token)
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
        if not desc or r.get("archived") or r.get("fork"):
            continue
        skip_keywords = [
            "tutorial", "course", "awesome-", "free-programming", "interview",
            "roadmap", "cheatsheet", "cheat-sheet",
            "面试", "教程", "面试题", "学习路线", "学习笔记", "刷题",
        ]
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


FEATURED_PATH = "output/git_featured.json"


def load_featured():
    if not os.path.exists(FEATURED_PATH):
        return set()
    with open(FEATURED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {item["full_name"] for item in data if item.get("full_name")}


def pick_repo(repos, featured):
    fresh = [r for r in repos if r["full_name"] not in featured]
    pool = fresh or repos
    scored = []
    for r in pool:
        stars = r["stars"]
        if stars > 80000 and fresh:
            continue
        weight = min(max(stars, 1), 5000) ** 0.5
        if 80 <= stars <= 20000:
            weight *= 1.5
        scored.append((weight, r))
    if not scored:
        scored = [(1.0, r) for r in pool]
    weights, items = zip(*scored)
    return random.choices(list(items), weights=list(weights), k=1)[0]


def main():
    from datetime import date
    token = github_api.token()
    print(f"GitHub API auth: {'token' if token else 'anonymous (60 req/hr)'}")

    repos = search_repos(token)
    if not repos:
        print("ERROR: No repos found", file=sys.stderr)
        sys.exit(1)

    featured = load_featured()
    print(f"  already featured: {len(featured)}")
    chosen = pick_repo(repos, featured)
    if chosen["full_name"] in featured:
        print("  WARNING: no fresh candidate, recycling a previously featured repo")

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

    print(f"selected: {chosen['full_name']} ({chosen['stars']} stars) - {chosen['description'][:60]}")
    print(f"output: output/git_collected.json")

if __name__ == "__main__":
    main()
