import json
import unittest

from util import slim_collected, word_count
from write import markdown_to_html
from git_search import pick_repo, load_featured
from image_style import article_prompt, cover_prompt, fit_crop, sanitize_scene, visual_motif


class SlimCollectedTest(unittest.TestCase):
    def test_valid_json_and_keeps_items(self):
        collected = {
            "date": "2026-09-03",
            "topics": ["AI"],
            "engine": "brave",
            "sources": [
                {
                    "query": "AI",
                    "results": [
                        {
                            "title": "T1",
                            "url": "https://example.com/1",
                            "description": "d" * 400,
                            "full_text": "f" * 2000,
                        }
                    ],
                }
            ],
        }
        text = slim_collected(collected, max_chars=800)
        data = json.loads(text)
        self.assertEqual(data["sources"][0]["results"][0]["title"], "T1")
        self.assertLessEqual(len(text), 800)

    def test_word_count_skips_headings(self):
        md = "# 标题\n\n正文八个字。"
        self.assertEqual(word_count(md), 6)


class MarkdownHtmlTest(unittest.TestCase):
    def test_ordered_list_strips_number(self):
        html = markdown_to_html("1. 第一项")
        self.assertIn("<ol", html)
        self.assertIn("第一项", html)
        self.assertNotIn("1. 第一项", html)

    def test_ul_to_ol_switch_closes_ul(self):
        html = markdown_to_html("- a\n1. b")
        self.assertIn("</ul>", html)
        self.assertIn("<ol", html)


class PickRepoTest(unittest.TestCase):
    def test_skips_featured(self):
        repos = [
            {"full_name": "old/repo", "stars": 1000, "id": 1},
            {"full_name": "new/repo", "stars": 200, "id": 2},
        ]
        chosen = pick_repo(repos, {"old/repo"})
        self.assertEqual(chosen["full_name"], "new/repo")


class FeaturedFileTest(unittest.TestCase):
    def test_load_featured(self):
        names = load_featured()
        self.assertIn("Snailclimb/JavaGuide", names)


class ImageStyleTest(unittest.TestCase):
    def test_sanitize_strips_screenshot(self):
        scene = sanitize_scene("JavaGuide GitHub 仓库页面截图，显示15万+ Star 和星标按钮")
        self.assertNotRegex(scene, r"截图|按钮|GitHub")

    def test_motif_for_memory(self):
        motif = visual_motif("AI数据处理的内存危机", "流式引擎")
        self.assertIn("pipe", motif.lower())

    def test_cover_prompt_wordless(self):
        prompt = cover_prompt("Polars 2.0 流式引擎", angle="内存", kind="daily")
        self.assertIn("Wordless", prompt)
        self.assertIn("pipes", prompt.lower())

    def test_article_prompt_varies_by_slot(self):
        a = article_prompt("左右对比图", "降价", index=0)
        b = article_prompt("左右对比图", "降价", index=1)
        self.assertNotEqual(a, b)
        scene = sanitize_scene("左右对比图")
        self.assertIn("diptych", scene)
        self.assertNotIn("对比图", scene)

    def test_fit_crop_size(self):
        from PIL import Image
        src = Image.new("RGB", (1200, 400), (10, 20, 30))
        out = fit_crop(src, 900, 383)
        self.assertEqual(out.size, (900, 383))


if __name__ == "__main__":
    unittest.main()
