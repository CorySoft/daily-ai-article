"""S4: Generate cover image for the 【开源精选】 article.
Reads output/git_plan.json, outputs output/git_cover.jpg.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from gen_cover import generate_cover


def main():
    with open("output/git_plan.json", encoding="utf-8") as f:
        plan = json.load(f)
    out_path = os.path.join(os.path.dirname(__file__), "..", "output", "git_cover.jpg")
    generate_cover(plan, out_path, kind="git")


if __name__ == "__main__":
    main()
