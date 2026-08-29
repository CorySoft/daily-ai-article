import json
import os
from datetime import date
import llm

PLAN_PROMPT = """你是公众号主编。基于以下检索素材做选题策划。

【素材】
{collected}

只输出JSON，不要其他文字。所有字段务必精简：
{{
  "topic": "标题（15字内）",
  "angle": "切入角度（60字内）",
  "core_view": "核心观点（60字内）",
  "outline": ["章1（8字内）","章2","章3","章4","章5"],
  "facts": ["事实1（20字内）","事实2","事实3"]
}}"""

def main():
    with open("output/collected.json", encoding="utf-8") as f:
        collected = json.load(f)
    collected_str = json.dumps(collected, ensure_ascii=False)[:6000]
    cut = collected_str.rfind(",")  # cut at a field boundary, not mid-string
    if cut > 200:
        collected_str = collected_str[:cut]
    print(f"Prompt size: {len(collected_str)} chars")
    prompt = PLAN_PROMPT.format(collected=collected_str)
    plan = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=8192)
    with open("output/plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"plan written: output/plan.json | topic: {plan.get('topic')}")

if __name__ == "__main__":
    main()
