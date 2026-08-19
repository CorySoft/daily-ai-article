# -*- coding: utf-8 -*-
"""Generate 900x383 cover image for daily-ai-article.
Reads topic from output/plan.json, outputs output/cover.png.
Follows wx_article safe-zone rules: key content within x∈[258,642].
"""
import json
import os
import textwrap
from PIL import Image, ImageDraw, ImageFont

FONT = "/system/fonts/NotoSansCJK-Regular.ttc"

BG = "#0F1322"
PANEL = "#1A2138"
BLUE = "#0F4C81"
CYAN = "#55C9EA"
TXT = "#E8EAF5"
SUB = "#8A93B5"

def font(sz, bold=False):
    return ImageFont.truetype(FONT, sz, index=1 if bold else 0)

def grid(d, w, h):
    for x in range(0, w, 26):
        for y in range(0, h, 26):
            d.point((x, y), fill="#162036")

def center_text(d, cx, y, text, f, fill, anchor="mm"):
    d.text((cx, y), text, font=f, fill=fill, anchor=anchor)

def wrap_title(title, max_chars=16):
    """Wrap title into lines of max_chars width."""
    lines = textwrap.wrap(title, width=max_chars)
    return lines[:3]

def main():
    plan_path = os.path.join(os.path.dirname(__file__), "..", "output", "plan.json")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "output")

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)

    topic = plan.get("topic", "AI Daily")
    angle = plan.get("angle", "")

    os.makedirs(out_dir, exist_ok=True)

    # --- Cover 900x383 (2.35:1) ---
    w, h = 900, 383
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    grid(d, w, h)

    # Decorative ellipses (safe to crop)
    d.ellipse([40, 90, 210, 260], outline=PANEL, width=2)
    d.ellipse([690, 90, 860, 260], outline=PANEL, width=2)

    cx = 450

    # Tag pill
    tag_text = "AI 每日精选"
    tag_f = font(16, True)
    bbox = d.textbbox((0, 0), tag_text, font=tag_f)
    tw = bbox[2] - bbox[0] + 44
    d.rounded_rectangle([cx - tw // 2, 16, cx + tw // 2, 56], radius=20, fill=BLUE)
    center_text(d, cx, 36, tag_text, tag_f, TXT)

    # Title (wrapped)
    title_lines = wrap_title(topic, max_chars=15)
    title_f = font(42, True)
    y_start = 80
    for i, line in enumerate(title_lines):
        center_text(d, cx, y_start + i * 56, line, title_f, TXT)

    # Divider
    div_y = y_start + len(title_lines) * 56 + 10
    d.line([(cx - 150, div_y), (cx + 150, div_y)], fill=CYAN, width=3)

    # Subtitle (angle, truncated)
    sub_text = angle[:36] + "..." if len(angle) > 36 else angle
    center_text(d, cx, div_y + 40, sub_text, font(20, True), CYAN)

    # Bottom tagline
    center_text(d, cx, 348, "AI 深度洞察 · 每日精选", font(16, True), SUB)

    cover_path = os.path.join(out_dir, "cover.png")
    img.save(cover_path)
    print(f"cover saved: {cover_path} {img.size}")

if __name__ == "__main__":
    main()
