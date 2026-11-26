"""S2: Plan a 【免费额度观察】 article from official free-tier candidates.

Reads output/free_collected.json, writes output/free_plan.json.
Every plan is anchored to a real candidate URL and to a vendor-owned domain,
and passes risk_verdict(recommend=True): this column recommends offers, so any
hit on the content red lines (including 灰产 / 薅羊毛) is fatal.
"""
import json
import re
import sys

import llm
import plan as daily_plan
from free_search import is_official
from util import risk_verdict, slim_collected

PLAN_PROMPT = """你是公众号「免费额度观察」主编。基于以下当日核实过的**厂商官方免费层/免费额度**素材，策划一篇有信息增量的文章。

【素材】（全部来自厂商官网域名，已过风险与时效门槛）
{collected}

【选题要求】
1. 选一条**当下仍有效、条款可核实、额度具体**的官方免费层；不要选新闻稿式"限量活动"。
2. 聚焦"谁能用、给多少、限制在哪、到期怎么办"，必须有可核对的数字或明确期限。
3. 只讲官方正常注册渠道。**严禁**批量注册、接码、养号、共享/合租账号、虚构身份、绕过地区限制等手法；素材里出现这类线索就换一条。
4. 标题用「免费额度 / 免费层 / 官方试用」这类中性表述，不要写「薅羊毛」「免费领会员」之类的词。

只输出 JSON，不要其他文字。所有字段务必精简：
{{
  "topic": "标题（15字内，有信息密度）",
  "angle": "切入角度（60字内）",
  "core_view": "核心判断（60字内）",
  "outline": ["章1（8字内）","章2","章3","章4","章5"],
  "facts": ["可核对事实1（20字内）","事实2","事实3"],
  "source_title": "素材标题（原样照抄）",
  "source_url": "素材URL（原样照抄）",
  "offer": {{
    "name": "免费层名称",
    "provider": "厂商名",
    "category": "token/agent/cloud/vps/phone 之一",
    "quota": "具体额度，必须带数字",
    "conditions": "资格与限制（60字内）",
    "valid_until": "有效期或「长期」",
    "official_url": "厂商官网条款/定价页 URL",
    "gotchas": "最容易踩的坑（40字内）"
  }}
}}"""


def _validate(plan_data, urls):
    problems = []
    if not str(plan_data.get("topic") or "").strip():
        problems.append("topic 缺失")
    if not daily_plan._match(plan_data.get("source_url"), urls):
        problems.append(f"source_url 不在达标素材中: {(plan_data.get('source_url') or '')[:60]}")

    offer = plan_data.get("offer") or {}
    for key in ("name", "provider", "quota", "conditions", "official_url"):
        if not str(offer.get(key) or "").strip():
            problems.append(f"offer.{key} 缺失")
    if not re.search(r"\d", str(offer.get("quota") or "")):
        problems.append("offer.quota 必须给出带数字的具体额度")
    if not is_official(offer.get("official_url") or ""):
        problems.append("offer.official_url 必须是厂商官方域名")
    if offer.get("category") not in ("token", "agent", "cloud", "vps", "phone", "custom"):
        problems.append("offer.category 不在允许范围")
    if len(plan_data.get("outline") or []) < 3:
        problems.append("outline 少于 3 章")

    # 推荐口径：subject 与 editorial 任一命中红线都硬拦，包括薅羊毛/接码/养号
    hard, soft = risk_verdict(
        [plan_data.get("source_title", ""), plan_data.get("source_url", ""),
         offer.get("name", ""), offer.get("official_url", ""), offer.get("conditions", "")],
        [plan_data.get("topic", ""), plan_data.get("angle", ""),
         plan_data.get("core_view", "")],
        True)
    if hard or soft:
        problems.append(f"命中内容安全红线 {hard or soft}：只推荐厂商官方正常渠道，换一条")
    return (not problems), problems


def main():
    with open("output/free_collected.json", encoding="utf-8") as f:
        collected = json.load(f)

    prompt = PLAN_PROMPT.format(collected=slim_collected(collected, max_chars=6000))
    urls = {it.get("url") for src in collected.get("sources", [])
            for it in src.get("results", [])}
    print(f"Prompt size: {len(prompt)} chars | candidates: {len(urls)}")

    plan_data = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=8192)
    ok, problems = _validate(plan_data, urls)
    if not ok:
        print(f"  选题未过硬门槛 {problems}，强制重试...", file=sys.stderr)
        retry = prompt + "\n\n【上一版选题不合格】" + "；".join(problems) + "。请换一条仍然达标的官方免费层重做。"
        plan_data = llm.chat_json([{"role": "user", "content": retry}], temperature=0.3, max_tokens=8192)
        ok, problems = _validate(plan_data, urls)
        if not ok:
            print(f"ERROR: plan 两次均未达到门槛: {problems}", file=sys.stderr)
            sys.exit(1)

    with open("output/free_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2)
    print(f"plan written: output/free_plan.json | topic: {plan_data.get('topic')} | "
          f"锚定: {(plan_data.get('source_url') or '')[:60]}")


if __name__ == "__main__":
    main()
