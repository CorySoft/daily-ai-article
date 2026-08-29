import json
import os
import time
import urllib.request

def get_config():
    return {
        "api_key": os.environ.get("LLM_API_KEY"),
        "model": os.environ.get("LLM_MODEL", "ep-20260810143613-s56fs"),
        "base_url": os.environ.get("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
    }

def chat(messages, temperature=0.7, max_tokens=3000, retries=3):
    cfg = get_config()
    if not cfg["api_key"]:
        raise SystemExit("缺少 LLM_API_KEY 环境变量")
    body = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"{cfg['base_url']}/chat/completions",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "User-Agent": "Mozilla/5.0 DailyAI/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read().decode("utf-8"))
            msg = resp["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content") or ""
            return _clean_content(content)
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  LLM 调用失败 (attempt {attempt+1}/{retries}): {e}")
                print(f"  {wait}s 后重试...")
                time.sleep(wait)
    raise last_err

def _clean_content(text):
    """Strip thinking tags and extra whitespace from model output."""
    import re
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL)
    return text.strip()

def _repair_json(text):
    """Try to fix common JSON issues."""
    import re
    # Remove markdown code fences
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # Insert missing commas between member key/value pairs
    text = re.sub(r'([}\]"]|[0-9])\n([ \t]*"[^"]+":)', r'\1,\n\2', text)
    # Insert missing commas between array/scalar string items ("..."\n"...")
    text = re.sub(r'"\n([ \t]*)(")', r'",\n\1\2', text)
    # Insert missing commas between bare-number / bool items
    text = re.sub(r'([0-9]\n[ \t]*)([0-9-])', r'\1,\2', text)
    # Fix unescaped newlines in string values
    text = re.sub(r'(?<=")\n(?=")', '\\n', text)
    return text

def _extract_json_candidates(text):
    """Extract candidate JSON snippets: from each '{' to its balanced '}'."""
    import re
    candidates = []
    for m in re.finditer(r'\{', text):
        depth = 0
        for idx in range(m.start(), len(text)):
            ch = text[idx]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidates.append(text[m.start():idx + 1])
                    break
    return candidates

def chat_json(messages, temperature=0.7, max_tokens=8192, retries=3):
    import re
    for attempt in range(retries):
        msgs = messages
        if attempt > 0:
            # Append a reproval note to break deterministic broken-JSON loops
            msgs = list(messages)
            extra = ("\n\n注意：你上一次输出不是合法 JSON（可能是缺失逗号或内容被截断）。"
                     "请重新输出一个完整、合法、只含 JSON 的结果，不要输出任何解释文字、"
                     "不要用代码围栏包裹，不要复述输入。")
            if msgs and msgs[-1].get("role") == "user":
                msgs[-1] = {"role": "user", "content": msgs[-1]["content"] + extra}
            else:
                msgs.append({"role": "user", "content": "请重新输出一个完整合法的 JSON。"})
        # Vary temperature per attempt to avoid identical broken outputs
        temp = min(temperature + attempt * 0.15, 1.2)
        text = chat(msgs, temperature=temp, max_tokens=max_tokens)
        text = _clean_content(text)

        candidates = _extract_json_candidates(text)
        if not candidates:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                candidates = [text[start:end + 1]]
        print(f"  JSON 候选: {len(candidates)} 块 (attempt {attempt+1}/{retries})")

        for candidate in candidates:
            for label, candidate in [("raw", candidate), ("repaired", _repair_json(candidate))]:
                try:
                    return json.loads(candidate, strict=False)
                except json.JSONDecodeError as e:
                    print(f"  JSON 解析失败 ({label}): {e}")
                try:
                    fixed = re.sub(r'[\x00-\x1f](?=[^"]*")', ' ', candidate)
                    return json.loads(fixed, strict=False)
                except json.JSONDecodeError as e:
                    print(f"  JSON 修复解析失败 ({label}): {e}")
        if attempt < retries - 1:
            print(f"  JSON 解析全部失败 (attempt {attempt+1}/{retries}), 重试...")
            continue
        raise ValueError(f"JSON 解析失败: {text[:600]}")
