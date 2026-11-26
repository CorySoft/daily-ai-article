"""第三条线（免费额度观察）的离线门槛测试：不碰 Brave / HN / LLM / 生图 API。"""
import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

import free_plan
import free_search
import free_write


def offer_item(**kwargs):
    item = {
        "title": "Free API credits for new developers",
        "url": "https://platform.openai.com/docs/pricing",
        "description": "Official free tier, 5 dollars in credits, 90 days",
        "source": "Brave",
        "pub_date": date.today().isoformat(),
        "hotness": 12,
    }
    item.update(kwargs)
    return item


def offer_plan(**kwargs):
    plan = {
        "topic": "OpenAI 免费额度能用多久",
        "angle": "从条款看免费额度的真实边界",
        "core_view": "官方免费层仍值得用，但别把它当长期方案",
        "outline": ["额度", "资格", "限制", "对比", "建议"],
        "facts": ["额度 5 美元", "90 天有效"],
        "source_title": "Free API credits for new developers",
        "source_url": "https://platform.openai.com/docs/pricing",
        "offer": {
            "name": "API free credits",
            "provider": "OpenAI",
            "category": "token",
            "quota": "5 美元额度 / 90 天",
            "conditions": "新注册账号，需绑定支付方式",
            "valid_until": "90 天",
            "official_url": "https://platform.openai.com/docs/pricing",
            "gotchas": "过期后按量计费",
        },
    }
    plan.update(kwargs)
    return plan


class GateTest(unittest.TestCase):
    def test_accepts_official_https_offer(self):
        ok, reason = free_search.gate(offer_item())
        self.assertTrue(ok, reason)

    def test_rejects_non_official_domain(self):
        ok, reason = free_search.gate(offer_item(url="https://blog.example.com/free-credits"))
        self.assertFalse(ok)
        self.assertIn("官方域名", reason)

    def test_rejects_github_repo_page(self):
        ok, reason = free_search.gate(offer_item(url="https://github.com/someone/free-tier-list"))
        self.assertFalse(ok)
        self.assertIn("仓库页", reason)

    def test_accepts_github_docs_page(self):
        ok, reason = free_search.gate(offer_item(
            url="https://docs.github.com/en/billing/managing-billing-for-github-copilot/about-billing-for-github-copilot"))
        self.assertTrue(ok, reason)

    def test_rejects_plain_http(self):
        ok, reason = free_search.gate(offer_item(url="http://platform.openai.com/docs/pricing"))
        self.assertFalse(ok)
        self.assertIn("HTTPS", reason)

    def test_rejects_grey_techniques(self):
        ok, reason = free_search.gate(offer_item(
            title="薅羊毛：批量注册领免费会员",
            description="接码平台批量注册",
        ))
        self.assertFalse(ok)
        self.assertTrue("risk" in reason or "灰产" in reason, reason)

    def test_rejects_stale_offer(self):
        old = (date.today() - timedelta(days=45)).isoformat()
        ok, reason = free_search.gate(offer_item(pub_date=old))
        self.assertFalse(ok)
        self.assertIn("过期", reason)

    def test_rejects_page_without_free_signal(self):
        ok, reason = free_search.gate(offer_item(
            title="Developer pricing", description="Pay as you go rates"))
        self.assertFalse(ok)
        self.assertIn("免费层信号", reason)

    def test_normalize_url_ignores_scheme_query_and_slash(self):
        self.assertEqual(
            free_search.normalize_url("https://platform.openai.com/docs/pricing/?utm=a"),
            free_search.normalize_url("http://platform.openai.com/docs/pricing"),
        )

    def test_mark_featured_dedups(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(free_search, "FEATURED_PATH", os.path.join(tmp, "featured.json")):
                free_search.mark_featured("https://platform.openai.com/docs/pricing/")
                free_search.mark_featured("https://platform.openai.com/docs/pricing?utm=b")
                free_search.mark_featured("https://www.volcano.com/free")
                self.assertEqual(len(free_search.load_featured()), 2)


class PlanValidateTest(unittest.TestCase):
    def setUp(self):
        self.urls = {offer_plan()["source_url"]}

    def test_accepts_well_anchored_plan(self):
        ok, problems = free_plan._validate(offer_plan(), self.urls)
        self.assertTrue(ok, problems)

    def test_rejects_unanchored_source_url(self):
        ok, problems = free_plan._validate(offer_plan(source_url="https://other.example/x"), self.urls)
        self.assertFalse(ok)
        self.assertTrue(any("source_url" in p for p in problems), problems)

    def test_rejects_vague_quota(self):
        ok, problems = free_plan._validate(offer_plan(
            offer={**offer_plan()["offer"], "quota": "很多免费额度"}), self.urls)
        self.assertFalse(ok)
        self.assertTrue(any("数字" in p for p in problems), problems)

    def test_rejects_non_official_terms_url(self):
        ok, problems = free_plan._validate(offer_plan(
            offer={**offer_plan()["offer"], "official_url": "https://deals.example.com/free"}),
            self.urls)
        self.assertFalse(ok)
        self.assertTrue(any("官方域名" in p for p in problems), problems)

    def test_rejects_grey_conditions(self):
        ok, problems = free_plan._validate(offer_plan(
            offer={**offer_plan()["offer"], "conditions": "批量注册并接码验证"}), self.urls)
        self.assertFalse(ok)
        self.assertTrue(any("红线" in p for p in problems), problems)

    def test_rejects_yangmao_title(self):
        ok, problems = free_plan._validate(offer_plan(topic="薅羊毛攻略"), self.urls)
        self.assertFalse(ok)
        self.assertTrue(any("红线" in p for p in problems), problems)

    def test_requires_outline(self):
        ok, problems = free_plan._validate(offer_plan(outline=["一", "二"]), self.urls)
        self.assertFalse(ok)
        self.assertTrue(any("outline" in p for p in problems), problems)


class StructureTest(unittest.TestCase):
    def test_structure_for_returns_one_of_rotating_skeletons(self):
        for day in (date(2026, 11, 14), date(2026, 11, 15), date(2026, 11, 16)):
            self.assertIn(free_write.structure_for(day), free_write.STRUCTURES)
        self.assertEqual(len(set(free_write.STRUCTURES)), 5)


if __name__ == "__main__":
    unittest.main()
