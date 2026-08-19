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
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  LLM 调用失败 (attempt {attempt+1}/{retries}): {e}")
                print(f"  {wait}s 后重试...")
                time.sleep(wait)
    raise last_err

def chat_json(messages, temperature=0.7, max_tokens=3000):
    text = chat(messages, temperature, max_tokens)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"模型未返回 JSON: {text[:300]}")
    return json.loads(text[start:end + 1])
