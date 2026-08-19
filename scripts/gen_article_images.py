# -*- coding: utf-8 -*-
"""Generate in-article images via Agnes Image API.
Reads image slot descriptions from output/images_meta.json,
outputs JPEG images to output/images/.
"""
import base64
import json
import os
import sys
import time
import urllib.request
from io import BytesIO
from PIL import Image

AGNES_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_MODEL = "agnes-image-2.0-flash"
IMG_W, IMG_H = 800, 450


def agnes_generate(prompt, api_key, size="800x450", timeout=300, retries=2):
    """Call Agnes Image API, return image bytes."""
    body = json.dumps({
        "model": AGNES_MODEL,
        "prompt": prompt,
        "size": size,
        "extra_body": {"response_format": "b64_json"},
    }).encode("utf-8")

    req = urllib.request.Request(
        AGNES_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 DailyAI/1.0",
        },
    )
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
            data = resp.get("data", [])
            if not data:
                raise ValueError(f"Agnes API returned no data: {resp}")
            item = data[0]
            if "b64_json" in item:
                return base64.b64decode(item["b64_json"])
            if "url" in item:
                with urllib.request.urlopen(item["url"], timeout=60) as r:
                    return r.read()
            raise ValueError(f"Agnes API response has neither url nor b64_json: {item}")
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(15 * (attempt + 1))  # backoff between retries
            print(f"  attempt {attempt+1}/{retries} failed: {e}", file=sys.stderr)
    raise last_err


def build_prompt(desc, topic):
    return (
        f"An editorial illustration for a Chinese tech article about: {topic}. "
        f"Scene: {desc}. "
        f"Style: clean modern tech illustration, flat design with subtle gradient, "
        f"soft lighting, professional, high quality. "
        f"No text or watermarks on the image. Aspect ratio 16:9."
    )


def main():
    base = os.path.join(os.path.dirname(__file__), "..")
    meta_path = os.path.join(base, "output", "images_meta.json")
    out_dir = os.path.join(base, "output", "images")
    plan_path = os.path.join(base, "output", "plan.json")

    if not os.path.exists(meta_path):
        print("WARNING: images_meta.json not found, no in-article images to generate", file=sys.stderr)
        sys.exit(0)

    with open(meta_path, encoding="utf-8") as f:
        slots = json.load(f)
    if not slots:
        print("No image slots, skipping in-article image generation")
        sys.exit(0)

    topic = ""
    if os.path.exists(plan_path):
        with open(plan_path, encoding="utf-8") as f:
            topic = json.load(f).get("topic", "")

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("WARNING: LLM_API_KEY not set, cannot generate images", file=sys.stderr)
        sys.exit(0)

    os.makedirs(out_dir, exist_ok=True)

    # Write a list of {desc, local_path} so the workflow can fill them in order
    mapping = []
    for i, slot in enumerate(slots):
        filename = f"img_{i}.jpg"
        path = os.path.join(out_dir, filename)
        prompt = build_prompt(slot["desc"], topic)
        try:
            print(f"Generating article image {i+1}/{len(slots)}: {slot['desc'][:30]}...")
            img_bytes = agnes_generate(prompt, api_key, size=f"{IMG_W}x{IMG_H}")
            img = Image.open(BytesIO(img_bytes)).convert("RGB").resize((IMG_W, IMG_H), Image.LANCZOS)
            img.save(path, "JPEG", quality=85, optimize=True)
            mapping.append({"desc": slot["desc"], "local_path": f"output/images/{filename}"})
            print(f"  saved: {path}")
        except Exception as e:
            print(f"WARNING: image {i+1} failed ({e}), skipping", file=sys.stderr)
        if i < len(slots) - 1:
            time.sleep(10)  # space out calls to respect 30 RPM rate limit

    with open(os.path.join(base, "output", "images_map.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"Generated {len(mapping)} images -> output/images_map.json")


if __name__ == "__main__":
    main()
