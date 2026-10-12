import json
import llm
from util import slim_collected

PLAN_PROMPT = """你是公众号主编。基于以下检索素材，策划一封「有热度、有前沿感」的科技主题。

【素材】(每条含 recency 时效信号，越接近当前日期越新鲜；source 标注来源)
{collected}

【选题要求】（重要，按顺序满足）
1. 优先选最近 3 天内发生的热点 / 最新发表的前沿成果 / 当日报头话题；素材里明文标注了 pub_date/age_hours/recency 的优先。
2. 避免“万金油旧话题”（如泛泛的 AI 趋势、众所周知的概念介绍、教程式综述）；只选有明确新闻事件、新发布、或新数据支撑的切入点。
3. 进入眼光：同一条新闻，选最有争议、最反直觉、最容易被大众忽略的侧面切入，而不是复述官方通稿。
4. 若素材跨来源都指向同一热点，选讨论最集中、时效最强的那条。

只输出JSON，不要其他文字。所有字段务必精简：
{{
  "topic": "标题（15字内，要有信息密度和吸引力）",
  "angle": "切入角度（60字内）",
  "core_view": "核心观点（60字内）",
  "outline": ["章1（8字内）","章2","章3","章4","章5"],
  "facts": ["事实1（20字内）","事实2","事实3"]
}}"""

def main():
    with open("output/collected.json", encoding="utf-8") as f:
        collected = json.load(f)
    collected_str = slim_collected(collected, max_chars=6000)
    print(f"Prompt size: {len(collected_str)} chars")
    prompt = PLAN_PROMPT.format(collected=collected_str)
    plan = llm.chat_json([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=8192)
    with open("output/plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"plan written: output/plan.json | topic: {plan.get('topic')}")

if __name__ == "__main__":
    main()
