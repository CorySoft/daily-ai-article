import json
import unittest

from util import slim_collected, word_count
from write import markdown_to_html, is_complete
from llm import _clean_content
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


class IsCompleteTest(unittest.TestCase):
    def test_complete_article(self):
        md = "# 标题\n\n## 章节1\n内容\n## 章节2\n内容\n## 章节3\n结尾。"
        self.assertTrue(is_complete(md))

    def test_truncated_missing_sections(self):
        md = "# 标题\n\n## 章节1\n内容\n结尾。"
        self.assertFalse(is_complete(md))

    def test_truncated_no_ending_punctuation(self):
        md = "# 标题\n\n## 章节1\n内容\n## 章节2\n内容\n## 章节3\n内容被截断"
        self.assertFalse(is_complete(md))


class CleanContentTest(unittest.TestCase):
    def test_strips_thinking_tag(self):
        self.assertEqual(_clean_content("开头<thinking>隐藏的思考过程</thinking>结尾"), "开头结尾")

    def test_strips_reasoning_tag(self):
        self.assertEqual(_clean_content("A<reasoning>r</reasoning>B"), "AB")

    def test_keeps_plain_text_unchanged(self):
        self.assertEqual(_clean_content("正常文本 thinking response 保留"), "正常文本 thinking response 保留")


class InjectSafetyTest(unittest.TestCase):
    def test_escapes_html_in_paragraph(self):
        html = markdown_to_html("正文 <script>alert(1)</script>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_escapes_amp_and_quotes(self):
        html = markdown_to_html('A&B "quote"')
        self.assertIn("A&amp;B", html)
        self.assertIn("&quot;quote&quot;", html)

    def test_escapes_image_desc_attribute(self):
        html = markdown_to_html('![配图描述：他说"好"]')
        self.assertIn('data-desc="他说&quot;好&quot;"', html)

    def test_escapes_code_block(self):
        html = markdown_to_html("```\n</pre><script>\n```")
        self.assertIn("&lt;/pre&gt;&lt;script&gt;", html)

    def test_link_protocol_whitelist(self):
        html = markdown_to_html("[安全](https://example.com/a?b=1&c=2)")
        self.assertIn('<a href="https://example.com/a?b=1&amp;c=2"', html)
        html2 = markdown_to_html("[危险](javascript:alert(1))")
        self.assertNotIn("<a href=\"javascript:", html2)


if __name__ == "__main__":
    unittest.main()
