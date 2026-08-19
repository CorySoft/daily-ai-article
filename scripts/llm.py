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
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # Fix unescaped newlines in string values
    text = re.sub(r'(?<=")\n(?=")', '\\n', text)
    return text

def chat_json(messages, temperature=0.7, max_tokens=8192, retries=3):
    for attempt in range(retries):
        text = chat(messages, temperature, max_tokens)
        text = _clean_content(text)
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            if attempt < retries - 1:
                print(f"  模型未返回 JSON (attempt {attempt+1}/{retries}), 重试...")
                continue
            raise ValueError(f"模型未返回 JSON: {text[:500]}")
        snippet = text[start:end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            repaired = _repair_json(snippet)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    print(f"  JSON 解析失败 (attempt {attempt+1}/{retries}), 重试...")
                    continue
                raise ValueError(f"JSON 解析失败: {repaired[:600]}")
