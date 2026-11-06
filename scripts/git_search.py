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
from util import risk_flags

# 质量与风险门槛：低于这线的仓库大多是刷星空壳，写进公众号既没价值也不安全
MIN_STARS = 200
MIN_FORKS = 3
MIN_SIZE_KB = 40          # 40KB 以下的"仓库"通常只有一份 README（引流页/文档壳）

# 2026-11-06 事故复盘：上一版用 stars:>30 + created:>3天 + "3 天内有 push ×1.8" 加权，
# 等于专门去捞新注册、刷星的灰产空壳，结果已经生成过待发草稿的项目里出现
# uncensored-nsfw-ai-video-api（涉黄）、Roblox-Aimbot（外挂）、两个 CVE PoC（漏洞利用）、
# microsoft-office（仿冒品牌）。现在改成先过硬门槛，再谈新鲜度。
QUERIES_BASE = [
    "stars:>200 topic:ai",
    "stars:>500 language:Python",
    "stars:>500 language:TypeScript",
    "stars:>400 language:Go",
    "stars:>400 language:Rust",
    "stars:>800 topic:mcp",
]


SKIP_KEYWORDS = [
    "tutorial", "course", "awesome-", "free-programming", "interview",
    "roadmap", "cheatsheet", "cheat-sheet",
    "面试", "教程", "面试题", "学习路线", "学习笔记", "刷题",
]


def gate(raw):
    """单个仓库候选的硬门槛。返回 (是否通过, 拒绝原因)。

    拆成纯函数是因为这段判断决定"公众号里出现什么项目"，必须能离线跑测试，
    而不是等 CI 真的去打 GitHub API 才发现把涉黄/外挂仓库放行了。
    """
    name = raw.get("full_name") or ""
    desc = raw.get("description") or ""
    topics = raw.get("topics") or []
    if not desc or raw.get("archived") or raw.get("fork"):
        return False, "无描述/已归档/fork"
    low = (name + " " + desc).lower()
    if any(kw in low for kw in SKIP_KEYWORDS):
        return False, "泛内容（教程/面试题/awesome 清单）"
    risky = risk_flags(name, desc, " ".join(topics))
    if risky:
        return False, "risk " + "/".join(risky)
    stars = raw.get("stargazers_count", 0) or 0
    forks = raw.get("forks_count", 0) or 0
    size_kb = raw.get("size", 0) or 0          # GitHub 的 size 单位就是 KB
    lic = (raw.get("license") or {}).get("spdx_id")
    if stars < MIN_STARS or forks < MIN_FORKS:
        return False, f"星数/分叉不足（{stars}/{forks}）"
    if size_kb < MIN_SIZE_KB:
        return False, f"仓库过小（{size_kb}KB，多半只有一份 README）"
    if not lic or lic == "NOASSERTION":
        return False, "无许可证，不适合写进「可以拿去用」的推荐稿"
    return True, ""


def search_repos(token=None):
    """Search for high-quality repos: real adoption, active, has substance."""
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc)
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    queries = [f"{q} pushed:>{week_ago}" for q in QUERIES_BASE]

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
        ok, reason = gate(r)
        if not ok:
            if reason.startswith("risk"):
                print(f"  [risk] 跳过 {r['full_name']}: {reason.split(' ', 1)[1]}")
            continue
        desc = r.get("description", "")
        topics = r.get("topics", [])
        filtered.append({
            "id": r["id"],
            "full_name": r["full_name"],
            "name": r["name"],
            "description": desc,
            "url": r["html_url"],
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0) or 0,
            "size_kb": r.get("size", 0) or 0,
            "language": r.get("language"),
            "topics": topics[:5],
            "license": (r.get("license") or {}).get("spdx_id"),
            "created_at": r.get("created_at", ""),
            "pushed_at": r.get("pushed_at", ""),
            "homepage": r.get("homepage", ""),
        })

    print(f"  [GitHub] total unique filtered: {len(filtered)} repos")
    return filtered


FEATURED_PATH = "output/git_featured.json"


def load_featured():
    """已推荐过的仓库名（小写）。GitHub 的 owner/repo 大小写不敏感，而 API 返回的
    拼写未必与 git_featured.json 里记录的一致（`Snailclimb/JavaGuide` vs `snailclimb/...`），
    按原样比较就可能把推荐过的仓库当成没推荐过。语料里暂未出现，属于潜在坑。"""
    if not os.path.exists(FEATURED_PATH):
        return set()
    with open(FEATURED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {item["full_name"].lower() for item in data if item.get("full_name")}


def pick_repo(repos, featured):
    fresh = [r for r in repos if r["full_name"].lower() not in featured]
    pool = fresh or repos
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    scored = []
    for r in pool:
        stars = r["stars"]
        if stars > 80000 and fresh:
            continue
        weight = min(max(stars, 1), 5000) ** 0.5
        if 80 <= stars <= 20000:
            weight *= 1.5
        # Freshness boost：最多 +30%。上一版给到 +80%，配合 stars:>30 的门槛
        # 等于把"新建三天、刚刷到几十星"的空壳顶到队首 —— 事故源头之一。
        try:
            pushed = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
            days = (now - pushed).total_seconds() / 86400
            if days >= 0:
                weight *= 1.0 + max(0.0, 0.3 * (1.0 - min(days, 7.0) / 7.0))
        except Exception:
            pass
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
        print("ERROR: 没有通过质量/风险门槛的候选仓库（MIN_STARS=%s MIN_FORKS=%s 需有许可证）"
              % (MIN_STARS, MIN_FORKS), file=sys.stderr)
        sys.exit(1)

    featured = load_featured()
    print(f"  already featured: {len(featured)}")
    chosen = pick_repo(repos, featured)
    if chosen["full_name"].lower() in featured:
        # 回收旧推荐 = 同一仓库被写第二遍，读者会看出来。宁可今天不出稿。
        print("ERROR: 候选已全部推荐过，拒绝重复出稿；扩大 QUERIES_BASE 或调低门槛后重跑",
              file=sys.stderr)
        sys.exit(1)
    risky = risk_flags(chosen["full_name"], chosen.get("description", ""))
    if risky:
        print(f"ERROR: 选中的仓库命中风险项 {risky}：{chosen['full_name']}", file=sys.stderr)
        sys.exit(1)

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
