# -*- coding: utf-8 -*-
"""Generate 900x383 cover image for daily-ai-article.
Uses Agnes Image API (agnes-image-2.0-flash) with PIL fallback.
Covers are pure concept images with NO text (per product requirement).
Reads topic from output/plan.json, outputs output/cover.jpg.
"""
import base64
import hashlib
import json
import os
import random
import sys
import time
import urllib.request
import urllib.error
from datetime import date
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

def _seed_from_article(topic, angle):
    """Deterministic per-article seed so the fallback cover differs between articles
    and by day, yet stays stable for the same article."""
    key = f"{date.today().isoformat()}|{topic}|{angle}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)


def _pil_palette(rng):
    """Pick one of a few navy/cyan-blue palettes for variety while staying on-brand."""
    palettes = [
        ("#123856", "#0A2E4E", "#55C9EA", "#0F4C81"),
        ("#0A2E4E", "#123856", "#0F4C81", "#55C9EA"),
        ("#16324F", "#0B2B45", "#7FD6F2", "#1B5A9B"),
        ("#0E2A4A", "#14365C", "#4FC3E8", "#2F6FB6"),
    ]
    return rng.choice(palettes)

def pil_fallback(topic, angle, out_path):
    """Generate a text-free abstract concept cover using PIL when API is unavailable.
    Layout varies per article (seeded), so consecutive fallback covers are NOT identical."""
    w, h = COVER_W, COVER_H
    rng = random.Random(_seed_from_article(topic, angle))
    orb_fill1, orb_fill2, ring1, ring2 = _pil_palette(rng)

    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    _pil_grid(d, w, h)

    # Top-left glow orb (cyan-family) and bottom-right orb (blue-family)
    o1 = (rng.randint(30, 90), rng.randint(90, 140), rng.randint(280, 340), rng.randint(320, 370))
    o2 = (rng.randint(590, 650), rng.randint(20, 60), rng.randint(850, 900), rng.randint(270, 320))
    d.ellipse(o1, fill=orb_fill1)
    d.ellipse(o2, fill=orb_fill2)
    d.ellipse([o1[0] + 45, o1[1] + 40, o1[2] - 25, o1[3] - 30], outline=ring1, width=3)
    d.ellipse([o2[0] + 50, o2[1] + 40, o2[2] - 30, o2[3] - 35], outline=ring2, width=3)

    # Concentric arcs at corners (circuit-like decoration), radii vary per article
    step = rng.randint(24, 34)
    for r in range(rng.randint(56, 72), rng.randint(150, 190), step):
        d.arc([w - r * 2, -r, w, r], 180, 270, fill=ring1, width=2)
        d.arc([-r, h - r, r, h + r], 0, 90, fill=ring2, width=2)

    # Node-network connection concept (randomized nodes)
    node_count = rng.randint(4, 7)
    nodes = [(rng.randint(60, 780), rng.randint(100, 290)) for _ in range(node_count)]
    nodes.sort(key=lambda p: p[0])
    for i in range(len(nodes) - 1):
        d.line([nodes[i], nodes[i + 1]], fill="#3D6B9E", width=2)
    for pt in nodes:
        r = rng.randint(4, 6)
        d.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill=ring1)

    # Accent rings (AI/abstract motion), varied size
    cx, cy = rng.randint(340, 440), rng.randint(110, 180)
    r_base = rng.randint(70, 100)
    d.ellipse([cx - r_base, cy - r_base, cx + r_base, cy + r_base], outline="#1E3A5F", width=2)
    d.ellipse([cx - r_base - 20, cy - r_base - 20, cx + r_base + 20, cy + r_base + 20], outline="#23486E", width=1)
    d.line([(cx - r_base - 20, cy), (cx + r_base + 20, cy)], fill="#1E3A5F", width=2)

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