import json
import os
from datetime import date
import llm

PLAN_PROMPT = """你是公众号主编。基于以下全网检索素材，做原创选题策划。

【检索素材】
{collected}

【要求】
1. 提取共同主题与高价值信息
2. 找出素材未充分回答的问题（原创切入点）
3. 确定原创切入角度和核心观点
4. 剔除重复、空泛内容

【输出 JSON】（严格精简，每个字段不超过100字，facts最多3条）
{{
  "topic": "选题标题（20字内）",
  "angle": "切入角度（80字内）",
  "core_view": "核心观点（100字内）",
  "outline": ["章节1", "章节2", "章节3", "章节4", "章节5"],
  "facts": [{{"fact": "事实（30字内）", "source": "来源", "confidence": "高/中/低"}}],
  "analysis_points": ["观点1（30字内）", "观点2（30字内）"],
  "gaps": ["问题（30字内）"]
}}"""

def main():
    with open("output/collected.json", encoding="utf-8") as f:
        collected = json.load(f)
    prompt = PLAN_PROMPT.format(collected=json.dumps(collected, ensure_ascii=False)[:6000])
    plan = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=8192)
    with open("output/plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"plan written: output/plan.json | topic: {plan.get('topic')}")

if __name__ == "__main__":
    main()
