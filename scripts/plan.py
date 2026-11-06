import json
import sys

import llm
from util import slim_collected

PLAN_PROMPT = """你是公众号主编。基于以下当日达标热点素材，策划一封「有热度、有前沿感」的科技主题文章。

【素材】(全部为当日通过热度门槛的热点；hotness：Hacker News 为讨论分，GitHub Trending 为今日新增星数，stars 为总星数)
{collected}

【选题要求】
1. 从上述素材中选当日热度最高、最有新闻价值的一条作为核心事件；同一事件选最有争议、最反直觉、最易被大众忽略的侧面切入，不复述官方通稿。
2. 避免万金油角度（泛泛趋势评论、常识科普、教程式综述）。
3. 若多条素材指向同一事件，说明讨论集中，优先选它。

只输出JSON，不要其他文字。所有字段务必精简：
{{
  "topic": "标题（15字内，要有信息密度和吸引力）",
  "angle": "切入角度（60字内）",
  "core_view": "核心观点（60字内）",
  "outline": ["章1（8字内）","章2","章3","章4","章5"],
  "facts": ["事实1（20字内）","事实2","事实3"],
  "source_title": "核心事件的素材标题（原样照抄）",
  "source_url": "核心事件的素材URL（原样照抄）"
}}"""

HN_A, HN_B = 80, 40


def _stars_of(it):
    v = it.get("stars")
    if v:
        return int(v)
    t = str(it.get("stars_text") or "").replace(",", "").strip()
    return int(t) if t.isdigit() else 0


def _within_3days(pub_date):
    from datetime import date
    if not pub_date:
        return False
    try:
        d = date.fromisoformat(str(pub_date)[:10])
    except ValueError:
        return False
    return (date.today() - d).days <= 3


def _grade(it):
    src = it.get("source")
    if src == "Hacker News":
        h = it.get("hotness") or 0
        return "A" if h >= HN_A else ("B" if h >= HN_B else "C")
    if src == "GitHub Trending":
        r = it.get("trending_rank")
        if r is None:
            # 抓取端未提供名次时退回星数，避免格式回退把好项目全判成 C 档
            n = _stars_of(it)
            return "A" if n >= 1000 else ("B" if n >= 200 else "C")
        return "A" if r <= 5 else ("B" if r <= 10 else "C")
    if src == "ArXiv":
        return "B" if _within_3days(it.get("pub_date")) else "C"
    return "B" if _within_3days(it.get("pub_date")) else "C"


def grade_materials(collected):
    """按热度给素材分级；A 档不足 3 条时逐级放宽，保证流水线不断。"""
    for src in collected.get("sources", []):
        for it in src.get("results", []):
            it["tier"] = _grade(it)
    for level in ("A", "B"):
        if count_tier(collected, level) >= 3:
            return collected, level
    return collected, "C"


def count_tier(collected, tier):
    return sum(1 for s in collected.get("sources", []) for it in s.get("results", []) if it.get("tier") == tier)


def by_tier(collected, tiers):
    out = []
    for src in collected.get("sources", []):
        items = [it for it in src.get("results", []) if it.get("tier") in tiers]
        if items:
            out.append({**src, "results": items})
    return {**collected, "sources": out}


def _match(s, urls):
    s_n = (s or "").rstrip("/#&")
    if not s_n:
        return False
    for u in urls:
        u_n = (u or "").rstrip("/#&")
        if s_n == u_n or (s_n and u_n and s_n[:40] == u_n[:40]):
            return True
    return False


def _validate(plan, urls):
    problems = []
    if not (plan.get("topic") or "").strip():
        problems.append("topic 缺失")
    if not _match(plan.get("source_url"), urls):
        problems.append(f"source_url 不在达标素材中: {(plan.get('source_url') or '')[:60]}")
    return (not problems), problems


def main():
    with open("output/collected.json", encoding="utf-8") as f:
        collected = json.load(f)

    collected, tier = grade_materials(collected)
    counts = {t: count_tier(collected, t) for t in "ABC"}
    allowed = {t for t in "ABC" if "ABC".index(t) <= "ABC".index(tier)}
    if tier != "A":
        print(f"警告: A 档素材不足（A={counts['A']}），门槛放宽到 {tier} 档（累计 {sum(counts[t] for t in allowed)} 条）",
              file=sys.stderr)
    else:
        print(f"热度门槛生效: A档 {counts['A']} 条（B {counts['B']} / C {counts['C']} 已剔除）")

    gated = by_tier(collected, allowed)
    collected_str = slim_collected(gated, max_chars=6000)
    print(f"Prompt size: {len(collected_str)} chars")
    urls = {it.get("url") for s in collected.get("sources", [])
            for it in s.get("results", []) if it.get("tier") in allowed}

    prompt = PLAN_PROMPT.format(collected=collected_str)
    plan = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=8192)
    ok, problems = _validate(plan, urls)
    if not ok:
        print(f"  选题未过硬门槛 {problems}，强制重试...", file=sys.stderr)
        plan = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=8192)
        ok, problems = _validate(plan, urls)
        if not ok:
            print(f"ERROR: plan 两次均未达到热度门槛: {problems}", file=sys.stderr)
            sys.exit(1)

    with open("output/plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"plan written: output/plan.json | topic: {plan.get('topic')} | 锚定: {(plan.get('source_title') or '')[:40]}")


if __name__ == "__main__":
    main()
