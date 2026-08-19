# -*- coding: utf-8 -*-
"""Replace pending image slots in article.json with jsdelivr CDN URLs.
Reads output/images_map.json (slot -> local path) and a jsdelivr base URL,
writes back article.json with real image src and thumb_url.
"""
import json
import os
import sys

def main():
    base = os.path.join(os.path.dirname(__file__), "..")
    article_path = os.path.join(base, "output", "article.json")
    map_path = os.path.join(base, "output", "images_map.json")

    if not os.path.exists(article_path):
        print("ERROR: article.json not found", file=sys.stderr)
        sys.exit(1)

    with open(article_path, encoding="utf-8") as f:
        data = json.load(f)

    # jsdelivr base: https://cdn.jsdelivr.net/gh/REPO@COMMIT/
    base_url = os.environ.get("CDN_BASE_URL", "")
    if not base_url:
        print("ERROR: CDN_BASE_URL not set", file=sys.stderr)
        sys.exit(1)

    # Build ordered list of URLs from images_map.json
    urls = []
    if os.path.exists(map_path):
        with open(map_path, encoding="utf-8") as f:
            img_list = json.load(f)
        for item in img_list:
            urls.append(base_url + item["local_path"])

    content = data["articles"][0]["content"]
    replaced = 0
    # Replace each IMAGESLOT_PENDING in order with the generated image URL
    for url in urls:
        if 'src="IMAGESLOT_PENDING"' in content:
            content = content.replace('src="IMAGESLOT_PENDING"', f'src="{url}"', 1)
            replaced += 1
    # Hide any remaining unfilled slots
    content = content.replace('src="IMAGESLOT_PENDING"', 'src=""')

    data["articles"][0]["content"] = content
    with open(article_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Filled image URLs: {replaced}/{len(urls)} ; thumb_url={data['articles'][0].get('thumb_url')}")

if __name__ == "__main__":
    main()
