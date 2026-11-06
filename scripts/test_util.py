import json
import os
import tempfile
import unittest

import llm
from util import slim_collected, word_count, is_complete
from util import ACCEPT_WORD_MIN, ACCEPT_WORD_MAX, TARGET_WORD_MIN, TARGET_WORD_MAX
from util import boilerplate_count, recent_outputs, risk_flags, risk_verdict, style_issues
import git_write
import plan
import write
from write import markdown_to_html, _citation_urls
from llm import _clean_content
import git_search
from git_search import gate, load_featured, pick_repo
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


class FeaturedFileTest(unittest.TestCase):
    """load_featured 不能依赖仓库里真实的 output/git_featured.json，也不能依赖工作目录。"""

    def test_load_featured_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "git_featured.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump([{"full_name": "Snailclimb/JavaGuide", "date": "2026-09-03"},
                           {"date": "2026-09-04"}], f)
            old = git_search.FEATURED_PATH
            git_search.FEATURED_PATH = path
            try:
                names = load_featured()
            finally:
                git_search.FEATURED_PATH = old
        self.assertIn("snailclimb/javaguide", names)
        self.assertEqual(len(names), 1)          # 缺 full_name 的脏条目要被忽略

    def test_pick_repo_skips_different_casing(self):
        repos = [{"full_name": "Snailclimb/JavaGuide", "stars": 1000, "id": 1, "pushed_at": ""},
                 {"full_name": "other/repo", "stars": 900, "id": 2, "pushed_at": ""}]
        chosen = pick_repo(repos, {"snailclimb/javaguide"})
        self.assertEqual(chosen["full_name"], "other/repo")


class RiskFlagsTest(unittest.TestCase):
    """2026-11-06 复盘：这些仓库已经真实生成过待发草稿，必须被拦下。"""

    PUBLISHED_BAD = {
        "wideeyededi/uncensored-nsfw-ai-video-api": "涉黄",
        "david-silvalab1993i0/Roblox-Aimbot-Smooth-Tracking-Auto-Aim-Script-2026": "游戏作弊",
        "DrWhax/unfairplay": "游戏作弊",
        "ctdal/cve-2026-41940-PoC": "攻击/漏洞利用",
        "eness/php2shell-CVE-2026-109618-CVE-2026-109619-PoC": "攻击/漏洞利用",
        "Nucleusanwish/microsoft-office": "仿冒品牌",
    }

    def test_previously_published_risky_repos_are_flagged(self):
        for name, label in self.PUBLISHED_BAD.items():
            self.assertIn(label, risk_flags(name), name)

    def test_ordinary_projects_are_not_flagged(self):
        for name in ["yt-dlp/yt-dlp", "ollama/ollama", "vitejs/vite", "pola-rs/polars",
                     "snailclimb/JavaGuide", "microsoft/vscode", "deepseek-ai/deepseek",
                     "MouseAngular/KMS-Pico"]:
            self.assertEqual(risk_flags(name), [], name)

    def test_description_level_risk(self):
        self.assertIn("盗版/破解", risk_flags("foo/bar", "免杀 payload builder, cracked keygen"))
        self.assertIn("灰产", risk_flags("foo/bar", "接码平台 刷量工具"))

    def test_defensive_security_title_is_flagged_too(self):
        """「警惕 KMS-Pico：…成为木马的伪装外衣」这类安全科普也会被拦。
        这是有意的：宁可 S7 红一次、人工核对后用 client 手动发，
        也不为了放过它把「木马」从红线里摘掉。"""
        title = "警惕 KMS-Pico：当“环境配置”成为木马的伪装外衣"
        self.assertEqual(risk_flags(title), ["攻击/漏洞利用"])
        self.assertEqual(risk_flags("KMS-Pico"), [])     # 仓库名本身是干净的，只有标题触发


class PlanTopicGateTest(unittest.TestCase):
    """S2 就要把违规选题拦掉，别等写完稿、生完图再在 S7 红。"""

    URLS = {"https://x.com/a"}

    def test_gray_market_topic_rejected(self):
        ok, problems = plan._validate(
            {"topic": "薅羊毛脚本", "core_view": "自动绑免税卡领两年会员", "source_url": "https://x.com/a"},
            self.URLS)
        self.assertFalse(ok)
        self.assertTrue(any("内容安全红线" in p for p in problems), problems)

    def test_security_news_topic_accepted(self):
        ok, problems = plan._validate(
            {"topic": "供应链攻击的暗面", "core_view": "npm 包里发现特洛伊木马",
             "source_url": "https://x.com/a"},
            self.URLS)
        self.assertTrue(ok, problems)

    def test_unanchored_topic_still_rejected(self):
        ok, problems = plan._validate({"topic": "普通选题", "source_url": "https://elsewhere.test/9"},
                                      self.URLS)
        self.assertFalse(ok)


class RiskVerdictTest(unittest.TestCase):
    """推荐口径与报道口径必须分开：日更写供应链木马是正当选题，开源精选推荐它就是事故。"""

    def test_recommend_column_blocks_on_headline(self):
        hard, soft = risk_verdict(["clean/name", "", ""],
                                  ["警惕 KMS-Pico：当“环境配置”成为木马的伪装外衣"], True)
        self.assertEqual(hard, ["攻击/漏洞利用"])
        self.assertEqual(soft, [])

    def test_news_column_allows_security_headlines(self):
        hard, soft = risk_verdict(["", "", ""],
                                  ["当代码仓库变成特洛伊木马：AI 时代供应链攻击的暗面"], False)
        self.assertEqual(hard, [])
        self.assertEqual(soft, ["攻击/漏洞利用"])

    def test_news_column_still_blocks_gray_and_adult(self):
        hard, _ = risk_verdict(["", "", ""], ["从“薅羊毛”到系统化套利：两年免费脚本攻防"], False)
        self.assertEqual(hard, ["灰产"])
        hard, _ = risk_verdict(["", "", ""], ["18+ 成人内容 API 拆解"], False)
        self.assertEqual(hard, ["涉黄"])

    def test_exploit_subject_is_a_note_in_news_mode(self):
        """日更报道一个 PoC / 恶意包是正当选题：降为告警，但写进 report.json 留痕。"""
        hard, soft = risk_verdict(["ctdal/cve-2026-41940-PoC", "", ""], ["一个值得关注的研究"], False)
        self.assertEqual(hard, [])
        self.assertEqual(soft, ["攻击/漏洞利用"])

    def test_recommend_mode_has_no_exemption(self):
        hard, soft = risk_verdict(["ctdal/cve-2026-41940-PoC", "", ""], ["一个新工具"], True)
        self.assertEqual(hard, ["攻击/漏洞利用"])
        self.assertEqual(soft, [])


class MarkFeaturedTest(unittest.TestCase):
    def test_mark_featured_is_case_insensitive_and_reentrant(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "git_featured.json")
            old = git_write.FEATURED_PATH
            git_write.FEATURED_PATH = path
            try:
                git_write.mark_featured("Foo/Bar")
                git_write.mark_featured("foo/bar")          # 大小写不同也不能记两条
                git_write.mark_featured("")                 # 空值直接忽略
            finally:
                git_write.FEATURED_PATH = old
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertEqual([x["full_name"] for x in data], ["Foo/Bar"])


class GateTest(unittest.TestCase):
    RAW_OK = {
        "id": 1, "full_name": "good/tool", "name": "tool", "description": "A real tool",
        "stargazers_count": 1200, "forks_count": 40, "size": 9000, "archived": False,
        "fork": False, "license": {"spdx_id": "MIT"}, "topics": ["cli"],
    }

    def test_healthy_repo_passes(self):
        ok, reason = gate(self.RAW_OK)
        self.assertTrue(ok, reason)

    def test_risky_repo_rejected(self):
        raw = dict(self.RAW_OK, full_name="x/uncensored-nsfw-api")
        ok, reason = gate(raw)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("risk"), reason)

    def test_starved_repo_rejected(self):
        raw = dict(self.RAW_OK, stargazers_count=40, forks_count=1)
        self.assertFalse(gate(raw)[0])

    def test_readme_only_shell_rejected(self):
        raw = dict(self.RAW_OK, size=8)          # 8KB
        self.assertFalse(gate(raw)[0])

    def test_no_license_rejected(self):
        raw = dict(self.RAW_OK, license=None)
        self.assertFalse(gate(raw)[0])

    def test_awesome_list_rejected(self):
        raw = dict(self.RAW_OK, description="Awesome list of interview questions")
        self.assertFalse(gate(raw)[0])


class CitationTest(unittest.TestCase):
    COLLECTED = {"sources": [{"query": "q", "results": [
        {"url": "https://unrelated.example/repo"},
        {"url": "https://event.example/news"},
    ]}]}

    def test_prefers_plan_anchor(self):
        urls = _citation_urls({"source_url": "https://event.example/news"}, self.COLLECTED)
        self.assertEqual(urls, "https://event.example/news")

    def test_anchor_only_never_shotguns(self):
        # 旧实现会把 collected 前 3 个 URL 全塞进去，与选题无关
        urls = _citation_urls({"source_url": "https://anchor.example/a"}, self.COLLECTED)
        self.assertNotIn("unrelated.example", urls)
        self.assertEqual(urls.split(), [urls])

    def test_falls_back_when_anchor_missing(self):
        urls = _citation_urls({}, self.COLLECTED)
        self.assertEqual(urls, "https://unrelated.example/repo")

    def test_empty_when_nothing_known(self):
        self.assertEqual(_citation_urls({}, {"sources": []}), "")


class ThresholdTest(unittest.TestCase):
    """提示词里写死的字数区间必须与验收常量一致，否则「模型照做仍被判失败」。"""

    def test_prompts_state_the_accept_gate(self):
        for mod in (write, git_write):
            p = mod.WRITE_PROMPT
            self.assertIn(f"{TARGET_WORD_MIN}~{TARGET_WORD_MAX} 字", p, mod.__name__)
            self.assertIn(f"低于 {ACCEPT_WORD_MIN} 字", p, mod.__name__)
            self.assertIn(f"超过 {ACCEPT_WORD_MAX} 字", p, mod.__name__)

    def test_target_sits_inside_accept(self):
        self.assertLessEqual(ACCEPT_WORD_MIN, TARGET_WORD_MIN)
        self.assertGreaterEqual(ACCEPT_WORD_MAX, TARGET_WORD_MAX)


class StyleIssuesTest(unittest.TestCase):
    def _md(self, heads=("第一个发现", "成本账"), body="正常叙述。", title="测试标题没有冒号"):
        secs = "\n".join(f"## {h}\n内容若干" for h in heads)
        return f"# {title}\n\n{body}\n{secs}\n收尾。"

    def test_clean_article_has_no_issue(self):
        self.assertEqual(style_issues(self._md(), [], []), [])

    def test_boilerplate_over_limit(self):
        md = self._md(body="值得注意的是，想象一下，让我们看看，可以看到，首先，其次，最后，完。")
        self.assertGreater(boilerplate_count(md), 4)
        self.assertTrue(any("套话" in p for p in style_issues(md)))

    def test_repeated_section_titles(self):
        prev = self._md(heads=("核心特性", "快速上手", "结语"))
        mine = self._md(heads=("核心特性", "快速上手", "别的"))
        self.assertTrue(any("雷同" in p for p in style_issues(mine, [prev])))

    def test_same_title_shape_as_all_recent(self):
        prev_titles = ["A：B", "C：D"]
        md = self._md(title="E：F")
        self.assertTrue(any("标题句式" in p for p in style_issues(md, [], prev_titles)))
        self.assertEqual(style_issues(md, [], ["C：D", "E 与 F"]), [])

    def test_recent_outputs_returns_bounded_texts(self):
        texts, titles = recent_outputs(days=3, kind="daily")
        self.assertLessEqual(len(texts), 3)
        self.assertTrue(all(isinstance(t, str) and t.strip() for t in texts))
        self.assertTrue(all(not t.startswith("#") for t in titles))


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

    def test_url_ending_is_complete(self):
        md = "# 标题\n\n## 章节1\n内容\n## 章节2\n内容\n## 章节3\n结尾一段。\n\n🔗 GitHub: https://github.com/a/b"
        self.assertTrue(is_complete(md))

    def test_injected_citation_line_is_not_truncation(self):
        """2026-11-06 回归：注入「参考来源」移到验收之后，把整条流水线判死。"""
        md = ("# 标题\n\n## 章节1\n内容\n## 章节2\n内容\n## 章节3\n结尾一段。"
              "\n\n> 参考来源：https://a.com/x https://b.org/y https://c.io/z")
        self.assertTrue(is_complete(md))

    def test_hr_then_citation_is_not_truncation(self):
        md = "# 标题\n\n## a\nx\n## b\ny\n## c\n收尾句。\n\n---\n\n*参考资料：Apple https://apple.com/n/*"
        self.assertTrue(is_complete(md))

    def test_bold_ending_counts_as_complete(self):
        md = "# 标题\n\n## a\nx\n## b\ny\n## c\n**钥匙握在你手里。**"
        self.assertTrue(is_complete(md))

    def test_ellipsis_ending_is_truncated(self):
        md = "# 标题\n\n## a\nx\n## b\ny\n## c\n话说一半……"
        self.assertFalse(is_complete(md))


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


class CleanContentTest(unittest.TestCase):
    def test_strips_thinking_tag(self):
        self.assertEqual(_clean_content("开头<thinking>隐藏的思考过程</thinking>结尾"), "开头结尾")

    def test_strips_reasoning_tag(self):
        self.assertEqual(_clean_content("A<reasoning>r</reasoning>B"), "AB")

    def test_keeps_plain_text_unchanged(self):
        self.assertEqual(_clean_content("正常文本 thinking response 保留"), "正常文本 thinking response 保留")


class ChatJsonRepairTest(unittest.TestCase):
    def test_repair_trailing_comma(self):
        self.assertEqual(llm._repair_json("{\"a\": 1, \"b\": 2,}"), "{\"a\": 1, \"b\": 2}")

    def test_repair_missing_comma(self):
        repaired = llm._repair_json("{\"a\": 1\n\"b\": 2}")
        self.assertIn("\"a\": 1,", repaired)

    def test_extract_balanced_candidates(self):
        cands = llm._extract_json_candidates('噪声{"a":1}尾巴{"c":2}')
        self.assertEqual(len(cands), 2)
        self.assertEqual(cands[0], '{"a":1}')
        self.assertEqual(cands[1], '{"c":2}')

    def test_chat_json_recovers_broken_output(self):
        def fake_chat(messages, **kw):
            return 'noise\n{"a": 1, "b": 2,}'

        orig = llm.chat
        llm.chat = fake_chat
        try:
            self.assertEqual(llm.chat_json([{"role": "user", "content": "x"}], retries=1), {"a": 1, "b": 2})
        finally:
            llm.chat = orig


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
