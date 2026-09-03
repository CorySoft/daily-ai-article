"""S2: Research the selected GitHub repo — fetch README + structure, analyze with LLM.
Reads output/git_collected.json, outputs output/git_plan.json.
"""
import base64
import json

import github_api


def fetch_readme(full_name, token=None):
    """Fetch raw README content."""
    try:
        data = github_api.get(f"/repos/{full_name}/readme", token)
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return content[:6000]  # cap at 6000 chars
    except Exception as e:
        print(f"  README fetch failed: {e}")
        return ""

def fetch_tree(full_name, token=None):
    """Fetch top-level file tree."""
    try:
        data = github_api.get(f"/repos/{full_name}/git/trees/HEAD?recursive=0", token)
        items = data.get("tree", [])
        lines = []
        for item in items[:50]:
            kind = "dir" if item["type"] == "tree" else "file"
            lines.append(f"  [{kind}] {item['path']} ({item.get('size', '')})")
        return "\n".join(lines)
    except Exception as e:
        print(f"  Tree fetch failed: {e}")
        return ""

RESEARCH_PROMPT = """你是资深技术编辑。分析以下开源项目，输出 JSON。

【项目信息】
name: {name}
full_name: {full_name}
description: {description}
stars: {stars}
forks: {forks}
language: {language}
topics: {topics}
license: {license}
homepage: {homepage}

【README 摘要】
{readme}

【目录结构】
{tree}

只输出 JSON，不要其他文字：
{{
  "topic": "推荐标题（15字内，有吸引力）",
  "angle": "切入角度（60字内）",
  "core_view": "核心推荐理由（60字内）",
  "tagline": "一句话导语（30字内，激发读者兴趣）",
  "highlights": ["亮点1（20字内）", "亮点2", "亮点3"],
  "use_cases": ["适用场景1", "适用场景2"],
  "quick_start": "如何快速使用（50字内）",
  "tech_notes": "技术亮点（50字内）"
}}"""

def main():
    import llm

    token = github_api.token()

    with open("output/git_collected.json", encoding="utf-8") as f:
        data = json.load(f)

    repo = data["selected"]
    print(f"Researching: {repo['full_name']} ({repo['stars']} stars)")

    # Fetch README and tree
    print("  Fetching README...")
    readme = fetch_readme(repo["full_name"], token)
    print(f"  README: {len(readme)} chars")

    print("  Fetching file tree...")
    tree = fetch_tree(repo["full_name"], token)
    print(f"  Tree: {len(tree)} chars")

    # Ask LLM to analyze
    prompt = RESEARCH_PROMPT.format(
        name=repo["name"],
        full_name=repo["full_name"],
        description=repo["description"],
        stars=repo["stars"],
        forks=repo["forks"],
        language=repo.get("language", "Unknown"),
        topics=", ".join(repo.get("topics", [])),
        license=repo.get("license", "Unknown"),
        homepage=repo.get("homepage", "None"),
        readme=readme[:4000],
        tree=tree[:2000],
    )
    print("  LLM analyzing...")
    plan = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=4096)

    # Enrich plan with repo metadata
    plan["repo"] = {
        "full_name": repo["full_name"],
        "url": repo["url"],
        "stars": repo["stars"],
        "forks": repo["forks"],
        "language": repo.get("language"),
        "license": repo.get("license"),
        "homepage": repo.get("homepage"),
    }

    with open("output/git_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    print(f"plan: output/git_plan.json | topic: {plan.get('topic')}")
    print(f"  highlights: {plan.get('highlights', [])}")

if __name__ == "__main__":
    main()
