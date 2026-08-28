# -*- coding: utf-8 -*-
"""Generate 900x383 cover image for daily-ai-article.
Uses Agnes Image API (agnes-image-2.0-flash) with PIL fallback.
Covers are pure concept images with NO text (per product requirement).
Reads topic from output/plan.json, outputs output/cover.jpg.
"""
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from PIL import Image, ImageDraw
from io import BytesIO

AGNES_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_MODEL = "agnes-image-2.0-flash"
COVER_W, COVER_H = 900, 383
OUT_NAME = "cover.jpg"

NO_TEXT_BLOCK = (
    "CRITICAL RULE: The image must be a pure abstract concept artwork. "
    "It MUST contain ABSOLUTELY NO text, no letters, no numbers, no words, "
    "no labels, no captions, no logos, no typography, no watermarks. "
    "The theme words below are visual inspiration only - never render them literally."
)

BG = "#0F1322"
PANEL = "#1A2138"
BLUE = "#0F4C81"
CYAN = "#55C9EA"

def _pil_grid(d, w, h):
    for x in range(0, w, 26):
        for y in range(0, h, 26):
            d.point((x, y), fill="#162036")

def _pil_gradient_overlay(img, alpha=40):
    """Apply a soft vertical depth gradient (darker at top, lighter at bottom)."""
    ov = Image.new("RGBA", (1, COVER_H))
    for y in range(COVER_H):
        t = y / COVER_H
        c = (26 + int(14 * t), 34 + int(18 * t), 54 + int(28 * t), alpha)
        ov.putpixel((0, y), c)
    img = img.convert("RGBA")
    img.alpha_composite(ov.resize((COVER_W, COVER_H)))
    return img.convert("RGB")

def pil_fallback(topic, angle, out_path):
    """Generate a text-free abstract concept cover using PIL when API is unavailable."""
    w, h = COVER_W, COVER_H
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    _pil_grid(d, w, h)

    # Top-left glow orb (cyan) and bottom-right orb (blue)
    d.ellipse([60, 110, 300, 350], fill="#123856")
    d.ellipse([620, 40, 880, 300], fill="#0A2E4E")
    d.ellipse([110, 160, 250, 300], outline=CYAN, width=3)
    d.ellipse([670, 90, 830, 250], outline=BLUE, width=3)

    # Concentric arcs at corners (circuit-like decoration)
    for r in range(60, 170, 28):
        d.arc([COVER_W - r * 2, -r, COVER_W, r], 180, 270, fill=CYAN, width=2)
        d.arc([-r, COVER_H - r, r, COVER_H + r], 0, 90, fill=BLUE, width=2)

    # Node-network connection concept
    nodes = [(180, 190), (450, 150), (520, 250), (720, 130), (760, 260)]
    for i in range(len(nodes) - 1):
        d.line([nodes[i], nodes[i + 1]], fill="#3D6B9E", width=2)
    for pt in nodes:
        d.ellipse([pt[0] - 5, pt[1] - 5, pt[0] + 5, pt[1] + 5], fill=CYAN)

    # Accent rings (AI/abstract motion)
    d.ellipse([360, 60, 540, 240], outline="#1E3A5F", width=2)
    d.ellipse([380, 80, 520, 220], outline="#23486E", width=1)
    d.line([(360, 150), (540, 150)], fill="#1E3A5F", width=2)

    img = _pil_gradient_overlay(img)
    img.save(out_path, "JPEG", quality=85, optimize=True)
    print(f"cover saved (PIL fallback, concept): {out_path} {img.size}")


def agnes_generate(prompt, api_key, size="1024x512", timeout=300, retries=2):
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
                time.sleep(15 * (attempt + 1))
            print(f"  cover attempt {attempt+1}/{retries} failed: {e}", file=sys.stderr)
    return None


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
        f"{NO_TEXT_BLOCK} "
        f"Abstract futuristic concept art for a WeChat banner. "
        f"Visual theme: {topic}. "
        f"Style: sleek dark navy gradient background with glowing cyan/blue light orbs, "
        f"subtle circuit/node network lines, futuristic AI aesthetic, depth and motion. "
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