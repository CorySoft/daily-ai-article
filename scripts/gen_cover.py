# -*- coding: utf-8 -*-
"""Generate 900x383 cover image for daily-ai-article.
Uses Agnes Image API (agnes-image-2.0-flash) with PIL fallback.
Reads topic from output/plan.json, outputs output/cover.png.
"""
import base64
import json
import os
import sys
import textwrap
import urllib.request
import urllib.error
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

AGNES_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_MODEL = "agnes-image-2.0-flash"
COVER_W, COVER_H = 900, 383
OUT_NAME = "cover.jpg"

# ── PIL fallback constants ──────────────────────────────────────────
FONT_PATHS = [
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

def _find_font():
    import glob
    for p in FONT_PATHS:
        if os.path.exists(p):
            return p
    for pattern in ["/usr/share/fonts/**/NotoSansCJK*.ttc",
                    "/usr/share/fonts/**/NotoSansCJK*.otf",
                    "/usr/share/fonts/**/*CJK*.ttf"]:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    return None

FONT = _find_font()

BG = "#0F1322"
PANEL = "#1A2138"
BLUE = "#0F4C81"
CYAN = "#55C9EA"
TXT = "#E8EAF5"
SUB = "#8A93B5"

def _pil_font(sz, bold=False):
    if FONT:
        try:
            return ImageFont.truetype(FONT, sz, index=1 if bold else 0)
        except Exception:
            pass
    return ImageFont.load_default()

def _pil_center_text(d, cx, y, text, f, fill, anchor="mm"):
    d.text((cx, y), text, font=f, fill=fill, anchor=anchor)

def _pil_grid(d, w, h):
    for x in range(0, w, 26):
        for y in range(0, h, 26):
            d.point((x, y), fill="#162036")

def pil_fallback(topic, angle, out_path):
    """Generate cover using PIL when API is unavailable."""
    if FONT is None:
        print("WARNING: No CJK font found. Chinese text will be garbled.", file=sys.stderr)
        print("  Install: sudo apt-get install -y fonts-noto-cjk", file=sys.stderr)

    w, h = COVER_W, COVER_H
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    _pil_grid(d, w, h)

    d.ellipse([40, 90, 210, 260], outline=PANEL, width=2)
    d.ellipse([690, 90, 860, 260], outline=PANEL, width=2)

    cx = 450
    tag_text = "AI 每日精选"
    tag_f = _pil_font(16, True)
    bbox = d.textbbox((0, 0), tag_text, font=tag_f)
    tw = bbox[2] - bbox[0] + 44
    d.rounded_rectangle([cx - tw // 2, 16, cx + tw // 2, 56], radius=20, fill=BLUE)
    _pil_center_text(d, cx, 36, tag_text, tag_f, TXT)

    lines = textwrap.wrap(topic, width=15)[:3]
    title_f = _pil_font(42, True)
    y_start = 80
    for i, line in enumerate(lines):
        _pil_center_text(d, cx, y_start + i * 56, line, title_f, TXT)

    div_y = y_start + len(lines) * 56 + 10
    d.line([(cx - 150, div_y), (cx + 150, div_y)], fill=CYAN, width=3)

    sub_text = angle[:36] + "..." if len(angle) > 36 else angle
    _pil_center_text(d, cx, div_y + 40, sub_text, _pil_font(20, True), CYAN)
    _pil_center_text(d, cx, 348, "AI 深度洞察 · 每日精选", _pil_font(16, True), SUB)

    img.save(out_path, "JPEG", quality=85, optimize=True)
    print(f"cover saved (PIL fallback): {out_path} {img.size}")


def agnes_generate(prompt, api_key, size="1024x512"):
    """Call Agnes Image API, return image bytes or None."""
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
    with urllib.request.urlopen(req, timeout=120) as r:
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


def main():
    plan_path = os.path.join(os.path.dirname(__file__), "..", "output", "plan.json")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    out_path = os.path.join(out_dir, OUT_NAME)

    if not os.path.exists(plan_path):
        print(f"ERROR: {plan_path} not found, skipping cover generation", file=sys.stderr)
        sys.exit(1)

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)

    topic = plan.get("topic", "AI Daily")
    angle = plan.get("angle", "")

    os.makedirs(out_dir, exist_ok=True)

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("WARNING: LLM_API_KEY not set, using PIL fallback", file=sys.stderr)
        pil_fallback(topic, angle, out_path)
        return

    prompt = (
        f"A modern, professional tech-themed banner image for a WeChat article. "
        f"Theme: {topic}. "
        f"Style: sleek dark blue gradient background with subtle circuit/grid patterns, "
        f"glowing cyan/blue accent elements, futuristic AI aesthetic. "
        f"No text on the image. "
        f"Aspect ratio 2.35:1 (wide landscape), clean and minimal composition."
    )

    try:
        print(f"Generating cover via Agnes Image API...")
        img_bytes = agnes_generate(prompt, api_key, size="1024x512")
        img = Image.open(BytesIO(img_bytes))
        img = img.convert("RGB").resize((COVER_W, COVER_H), Image.LANCZOS)
        img.save(out_path, "JPEG", quality=85, optimize=True)
        print(f"cover saved (Agnes API): {out_path} {img.size}")
    except Exception as e:
        print(f"WARNING: Agnes Image API failed ({e}), using PIL fallback", file=sys.stderr)
        pil_fallback(topic, angle, out_path)


if __name__ == "__main__":
    main()
