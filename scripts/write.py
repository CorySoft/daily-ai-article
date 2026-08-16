import json
import os
import re
import urllib.request
from datetime import date

def call_llm(prompt, api_key, model="gpt-4o-mini", base_url="https://api.openai.com/v1"):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return resp["choices"][0]["message"]["content"]

def build_prompt(collected):
    items = "\n".join(
        f"- {n['title']} ({n['url']})" for n in collected["news"]
    )
    return f"""你是一名中文公众号编辑。请根据以下当日信息，写一篇适合微信公众号发布的文章。

要求：
1. 第一行是文章标题，以 # 开头，例如 # 标题
2. 第二行开始是正文
3. 正文围绕当日热点展开，分小标题组织（用 ## 表示小节）
4. 语言通俗、专业、有观点
5. 结尾有简短的总结
6. 除标题外不要输出任何说明
7. 正文控制在 800 字以内

当日信息（{collected['date']}，来源 {collected['source']}）：
{items}"""

def split_title(article):
    lines = article.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        title = lines[0].lstrip().lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()
        return title or date.today().isoformat(), body
    return date.today().isoformat(), article

def markdown_to_html(md):
    html_lines = []
    for line in md.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            html_lines.append(f"<h{level}>{m.group(2)}</h{level}>")
        elif re.match(r"^[-*+]\s+", line):
            html_lines.append(f"<p>{line.strip()[2:].strip()}</p>")
        else:
            html_lines.append(f"<p>{line}</p>")
    return "".join(html_lines)

def main():
    with open("output/collected.json", encoding="utf-8") as f:
        collected = json.load(f)
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    if not api_key:
        raise SystemExit("缺少 LLM_API_KEY 环境变量")
    article = call_llm(build_prompt(collected), api_key, model, base_url).strip()
    title, body = split_title(article)
    with open(f"output/{date.today()}.md", "w", encoding="utf-8") as f:
        f.write(article)

    payload = {
        "draft": True,
        "articles": [{
            "title": title,
            "author": os.environ.get("ARTICLE_AUTHOR", "小编"),
            "digest": os.environ.get("ARTICLE_DIGEST", ""),
            "content": markdown_to_html(body),
        }],
    }
    with open("output/article.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"article written: output/{date.today()}.md ; publish payload: output/article.json")

if __name__ == "__main__":
    main()