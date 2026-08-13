from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_morning_radar.analysis import _validate_ai, analyze
from ai_morning_radar.config import load_config
from ai_morning_radar.pipeline import _load_fixture
from ai_morning_radar.scoring import calculate_sentiment


class AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.market, self.news, self.events = _load_fixture()

    def test_force_fallback_covers_all_sectors(self) -> None:
        score, label, _ = calculate_sentiment(self.market, self.config)
        summary, points, impacts, mode, _ = analyze(
            self.market, self.news, self.events, self.config, score, label, force_fallback=True
        )
        self.assertEqual(mode, "规则模板")
        self.assertEqual(len(impacts), 7)
        self.assertTrue(summary)
        self.assertTrue(points)

    def test_unknown_evidence_is_rejected(self) -> None:
        impacts = []
        for sector in self.config["sector_keywords"]:
            impacts.append({"sector": sector, "direction": "中性", "strength": 1, "horizon": "当日", "reason": "测试", "evidence_ids": ["MADE-UP"], "kind": "推断"})
        with self.assertRaises(ValueError):
            _validate_ai({"one_line_summary": "测试", "auction_points": ["测试"], "sector_impacts": impacts}, {"MKT-NVDA"})

    def test_unsourced_number_is_rejected(self) -> None:
        impacts = []
        for sector in self.config["sector_keywords"]:
            impacts.append({"sector": sector, "direction": "中性", "strength": 1, "horizon": "当日", "reason": "预计上涨3%", "evidence_ids": [], "kind": "推断"})
        with self.assertRaisesRegex(ValueError, "无证据来源"):
            _validate_ai({"one_line_summary": "测试", "auction_points": ["测试"], "sector_impacts": impacts}, {"MKT-NVDA"})

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=False)
    @patch("ai_morning_radar.analysis.urllib.request.urlopen", side_effect=TimeoutError("timeout"))
    def test_model_timeout_falls_back(self, _urlopen) -> None:
        score, label, _ = calculate_sentiment(self.market, self.config)
        _, _, impacts, mode, warnings = analyze(self.market, self.news, self.events, self.config, score, label)
        self.assertEqual(mode, "规则模板")
        self.assertEqual(len(impacts), 7)
        self.assertTrue(any("AI分析失败" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()
