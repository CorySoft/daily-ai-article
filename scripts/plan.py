import json
import os
from datetime import date
import llm

PLAN_PROMPT = """你是公众号主编。基于以下全网检索素材，做原创选题策划（只做内部分析，不写正文）。

【检索素材】
{collected}

【要求】
1. 提取共同主题与高价值信息
2. 找出素材未充分回答的问题（这是原创切入点）
3. 确定一个原创切入角度和核心观点
4. 区分"已证实事实"与"分析/推测"
5. 剔除重复、空泛、无依据内容

【输出 JSON】
{{
  "topic": "选题标题",
  "angle": "原创切入角度",
  "core_view": "核心观点",
  "outline": ["章节1小标题", "章节2小标题", "章节3小标题", "章节4小标题", "章节5小标题"],
  "facts": [{{"fact": "已证实事实", "source": "来源", "confidence": "高/中/低"}}],
  "analysis_points": ["分析/观点点1", "分析/观点点2"],
  "gaps": ["素材未回答的问题"]
}}"""

def main():
    with open("output/collected.json", encoding="utf-8") as f:
        collected = json.load(f)
    prompt = PLAN_PROMPT.format(collected=json.dumps(collected, ensure_ascii=False)[:6000])
    plan = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.5)
    with open("output/plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"plan written: output/plan.json | topic: {plan.get('topic')}")

if __name__ == "__main__":
    main()
