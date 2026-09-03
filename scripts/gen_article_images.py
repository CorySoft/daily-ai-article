# -*- coding: utf-8 -*-
"""Generate in-article images via Agnes Image API.
Reads image slot descriptions from output/images_meta.json,
outputs JPEG images to output/images/.
If the Agnes Image API fails for a slot, falls back to deterministic,
per-article seeded procedural concept art (same renderer as the cover),
so published articles always carry fresh visuals and never stale images.
"""
import hashlib
import json
import os
import sys
import time
from datetime import date
from io import BytesIO
from PIL import Image

from gen_cover import render_concept, agnes_generate
from image_style import article_prompt, fit_crop

IMG_W, IMG_H = 800, 450


def _slot_seed(topic, desc, index):
    """Deterministic per-article/per-slot seed so concept fallbacks differ between
    articles, days and slots, yet stay stable for the same slot."""
    key = f"{date.today().isoformat()}|{topic}|{desc}|{index}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)


def build_prompt(desc, topic, index=0):
    return article_prompt(desc, topic, index=index)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="", help="File prefix (e.g. 'git_' )")
    args = parser.parse_args()
    prefix = args.prefix

    base = os.path.join(os.path.dirname(__file__), "..")
    meta_path = os.path.join(base, "output", f"{prefix}images_meta.json")
    out_dir = os.path.join(base, "output", f"{prefix}images")
    plan_path = os.path.join(base, "output", f"{prefix}plan.json")

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
        print("WARNING: LLM_API_KEY not set, using concept fallback for all slots", file=sys.stderr)

    os.makedirs(out_dir, exist_ok=True)

    # Write a list of {desc, local_path} so the workflow can fill them in order
    mapping = []
    for i, slot in enumerate(slots):
        filename = f"img_{i}.jpg"
        path = os.path.join(out_dir, filename)
        prompt = build_prompt(slot["desc"], topic, index=i)
        seed = _slot_seed(topic, slot["desc"], i)
        try:
            if not api_key:
                raise RuntimeError("LLM_API_KEY not set")
            print(f"Generating article image {i+1}/{len(slots)}: {slot['desc'][:30]}...")
            img_bytes = agnes_generate(prompt, api_key, size="1024x576")
            if not img_bytes:
                raise RuntimeError("Agnes returned no image")
            img = fit_crop(Image.open(BytesIO(img_bytes)), IMG_W, IMG_H)
            img.save(path, "JPEG", quality=88, optimize=True)
            mapping.append({"desc": slot["desc"], "local_path": f"output/{prefix}images/{filename}"})
            print(f"  saved: {path}")
        except Exception as e:
            print(f"WARNING: image {i+1} via Agnes failed ({e}); using seeded concept fallback", file=sys.stderr)
            img = render_concept(seed, IMG_W, IMG_H, topic=topic, angle=slot["desc"])
            img.save(path, "JPEG", quality=85, optimize=True)
            mapping.append({"desc": slot["desc"], "local_path": f"output/{prefix}images/{filename}"})
            print(f"  saved (concept fallback): {path}")
        if i < len(slots) - 1:
            time.sleep(10)  # space out calls to respect 30 RPM rate limit

    # Safety net: if even a slot fallback failed (disk/encoding issue), abort instead
    # of silently reusing stale or mismatched images.
    if len(mapping) < len(slots):
        print(
            f"ERROR: only {len(mapping)}/{len(slots)} article images are present "
            f"(even concept fallback failed). Aborting so a stale or mismatched image "
            f"is not published.", file=sys.stderr
        )
        sys.exit(1)

    with open(os.path.join(base, "output", f"{prefix}images_map.json"), "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"Generated {len(mapping)} images -> output/{prefix}images_map.json")


if __name__ == "__main__":
    main()
