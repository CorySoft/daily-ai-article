"""S4: Generate cover image for the 【免费额度观察】 article.
Reads output/free_plan.json, outputs output/free_cover.jpg.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from gen_cover import generate_cover


def main():
    base = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(base, "output", "free_plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    out_path = os.path.join(base, "output", "free_cover.jpg")
    generate_cover(plan, out_path, kind="free")


if __name__ == "__main__":
    main()
