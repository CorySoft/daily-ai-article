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
from datetime import date
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter
from io import BytesIO
from image_style import cover_prompt, fit_crop

AGNES_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_MODEL = "agnes-image-2.0-flash"
COVER_W, COVER_H = 900, 383
OUT_NAME = "cover.jpg"

def _ramp(pal):
    """Expand a list of RGB stops into a 768-int palette (grayscale value -> color)."""
    flat = []
    n = len(pal) - 1
    for i in range(256):
        t = i / 255.0 * n
        lo = int(t)
        hi = min(lo + 1, n)
        a, b = pal[lo], pal[hi]
        f = t - lo
        flat.extend(int(a[k] + (b[k] - a[k]) * f) for k in range(3))
    return flat


_PALETTES = [
    [(11, 27, 51), (20, 44, 84), (23, 66, 110), (39, 122, 178), (85, 201, 234), (167, 230, 255)],
    [(13, 17, 36), (31, 36, 100), (68, 60, 150), (130, 104, 220), (184, 156, 255), (222, 200, 255)],
    [(9, 28, 44), (13, 48, 66), (23, 88, 100), (42, 168, 160), (105, 231, 210), (199, 255, 238)],
    [(18, 16, 31), (43, 24, 64), (124, 58, 102), (224, 122, 95), (242, 201, 160), (255, 238, 214)],
]


def _value_noise(rng, w, h, gx, gy):
    """Smooth organic noise: upscaled random grid (value noise) -> 'L' image."""
    small = Image.new("L", (gx, gy))
    small.putdata([rng.randint(0, 255) for _ in range(gx * gy)])
    return small.resize((w, h), Image.BICUBIC)


def _seed_from_article(topic, angle):
    """Deterministic per-article seed so the fallback cover differs between articles
    and by day, yet stays stable for the same article."""
    key = f"{date.today().isoformat()}|{topic}|{angle}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)


def _palette_for(topic, angle, rng):
    blob = f"{topic} {angle}".lower()
    if any(k in blob for k in ("rust", "java", "降价", "warm")):
        return _PALETTES[3]
    if any(k in blob for k in ("开源", "安全", "隐私", "github")):
        return _PALETTES[1]
    if any(k in blob for k in ("内存", "stream", "流式", "polars")):
        return _PALETTES[2]
    return rng.choice(_PALETTES)


def render_concept(seed, w, h, topic="", angle=""):
    rng = random.Random(seed)
    pal = _palette_for(topic, angle, rng)
    ramp = _ramp(pal)
    dim = float(min(w, h))

    # Organic cloud field: two value-noise octaves averaged + side depth shading
    field = ImageChops.add(
        _value_noise(rng, w, h, 9, 5),
        _value_noise(rng, w, h, 27, 14),
        scale=2,
    )
    depth = Image.new("L", (w, 1))
    depth.putdata([int(205 - 90 * (x / w)) for x in range(w)])
    depth = depth.resize((w, h))
    base = ImageChops.multiply(field, depth).convert("P")
    base.putpalette(ramp)
    base = base.convert("RGBA")

    # Soft glow bokeh: wide blurred translucent orbs + small bright dots
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for _ in range(rng.randint(8, 13)):
        r = int(dim * rng.uniform(0.06, 0.45))
        x = rng.randint(-r, w + r)
        y = rng.randint(-r, h + r)
        col = pal[min(len(pal) - 1, int(rng.uniform(1.5, len(pal))))]
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (rng.randint(16, 50),))
    ov = ov.filter(ImageFilter.GaussianBlur(rng.uniform(14, 34)))

    ov2 = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(ov2)
    for _ in range(rng.randint(16, 30)):
        x = int(rng.uniform(0, w))
        y = int(rng.uniform(0, h))
        r = int(dim * rng.uniform(0.006, 0.03))
        col = pal[rng.randint(2, len(pal) - 1)]
        d2.ellipse([x - r, y - r, x + r, y + r], fill=col + (rng.randint(40, 115),))
    ov2 = ov2.filter(ImageFilter.GaussianBlur(rng.uniform(1.2, 3.0)))

    base = Image.alpha_composite(Image.alpha_composite(base, ov), ov2)

    # Energy-flow ribbons (neural/particle traces)
    fov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fov)
    for _ in range(rng.randint(3, 6)):
        x = rng.uniform(-w * 0.1, w * 0.3)
        y = rng.uniform(0, h)
        pts = []
        for _ in range(rng.randint(18, 40)):
            x += rng.uniform(-w * 0.026, w * 0.026)
            y += rng.uniform(-h * 0.02, h * 0.02)
            pts.append((x, y))
        col = pal[rng.randint(2, len(pal) - 1)]
        for i in range(len(pts) - 1):
            fd.line([pts[i], pts[i + 1]], fill=col + (rng.randint(24, 62),), width=rng.randint(1, 2))
    fov = fov.filter(ImageFilter.GaussianBlur(0.8))
    base = Image.alpha_composite(base, fov)

    # Subtle film grain
    gn = _value_noise(rng, w, h, max(6, w // 10), max(4, h // 10))
    a = gn.point(lambda v: 0 if v < 180 else (v - 180) // 3)
    grain = Image.merge(
        "RGBA",
        (Image.new("L", (w, h), 255), Image.new("L", (w, h), 255), Image.new("L", (w, h), 255), a),
    )
    base = Image.alpha_composite(base, grain)

    # Vignette darkening toward the edges
    dark = ImageEnhance.Brightness(base).enhance(0.55)
    mask = Image.new("L", (w, h))
    ImageDraw.Draw(mask).ellipse([-w * 0.18, -h * 0.30, w * 1.18, h * 1.30], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(int(dim * 0.22 + 1)))
    base = Image.composite(base, dark, mask)
    return base.convert("RGB")


def pil_fallback(topic, angle, out_path):
    """Generate a text-free abstract concept cover using PIL when API is unavailable.
    Layout varies per article (seeded), so consecutive fallback covers are NOT identical."""
    img = render_concept(_seed_from_article(topic, angle), COVER_W, COVER_H, topic=topic, angle=angle)
    img.save(out_path, "JPEG", quality=85, optimize=True)
    print(f"cover saved (PIL fallback, concept art): {out_path} {img.size}")


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


def save_cover_bytes(img_bytes, out_path):
    img = Image.open(BytesIO(img_bytes))
    img = fit_crop(img, COVER_W, COVER_H)
    img.save(out_path, "JPEG", quality=88, optimize=True)
    return img.size


def generate_cover(plan, out_path, kind="daily"):
    topic = plan.get("topic", "AI Daily")
    angle = plan.get("tagline") or plan.get("angle", "")
    language = (plan.get("repo") or {}).get("language", "")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("WARNING: LLM_API_KEY not set, using PIL fallback", file=sys.stderr)
        pil_fallback(topic, angle, out_path)
        return

    prompt = cover_prompt(topic, angle=angle, language=language, kind=kind)
    try:
        print(f"Generating {kind} cover via Agnes Image API...")
        img_bytes = agnes_generate(prompt, api_key, size="1024x512")
        if not img_bytes:
            raise RuntimeError("Agnes returned no image")
        size = save_cover_bytes(img_bytes, out_path)
        print(f"cover saved (Agnes API): {out_path} {size}")
    except Exception as e:
        print(f"WARNING: Agnes Image API failed ({e}), using PIL fallback", file=sys.stderr)
        pil_fallback(topic, angle, out_path)


def main():
    plan_path = os.path.join(os.path.dirname(__file__), "..", "output", "plan.json")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    out_path = os.path.join(out_dir, OUT_NAME)

    if not os.path.exists(plan_path):
        print(f"ERROR: {plan_path} not found, skipping cover generation", file=sys.stderr)
        sys.exit(1)

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    generate_cover(plan, out_path, kind="daily")


if __name__ == "__main__":
    main()