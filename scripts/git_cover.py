"""S4: Generate cover image for the 【开源精选】 article.
Reads output/git_plan.json, outputs output/cover.jpg.
Covers are pure concept images with NO text.
Imports Agnes API logic from gen_cover.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from gen_cover import agnes_generate, pil_fallback, NO_TEXT_BLOCK, COVER_W, COVER_H
from io import BytesIO
from PIL import Image

def main():
    with open("output/git_plan.json", encoding="utf-8") as f:
        plan = json.load(f)

    topic = plan.get("topic", "Open Source")
    tagline = plan.get("tagline", plan.get("angle", ""))
    repo_name = plan.get("repo", {}).get("full_name", "")
    language = plan.get("repo", {}).get("language", "")

    out_path = os.path.join(os.path.dirname(__file__), "..", "output", "cover.jpg")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("WARNING: LLM_API_KEY not set, using PIL fallback", file=sys.stderr)
        pil_fallback(topic, tagline, out_path)
        return

    lang_hint = f"Programming language: {language}. " if language else ""
    prompt = (
        f"{NO_TEXT_BLOCK} "
        f"Abstract futuristic concept art for a WeChat banner about an open-source software project. "
        f"{lang_hint}"
        f"Visual theme: {topic}. "
        f"Style: sleek dark navy gradient background with glowing cyan/blue light orbs, "
        f"subtle code/circuit node network lines, futuristic developer aesthetic, depth and motion. "
        f"Aspect ratio 2.35:1 (wide landscape), clean and minimal composition."
    )

    try:
        print(f"Generating cover via Agnes Image API for {repo_name}...")
        img_bytes = agnes_generate(prompt, api_key, size="1024x512")
        img = Image.open(BytesIO(img_bytes))
        img = img.convert("RGB").resize((COVER_W, COVER_H), Image.LANCZOS)
        img.save(out_path, "JPEG", quality=85, optimize=True)
        print(f"cover saved (Agnes): {out_path} {img.size}")
    except Exception as e:
        print(f"WARNING: Agnes Image API failed ({e}), using PIL fallback", file=sys.stderr)
        pil_fallback(topic, tagline, out_path)

if __name__ == "__main__":
    main()