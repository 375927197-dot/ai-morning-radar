from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_morning_radar.collectors.market import normalize_snapshot
from ai_morning_radar.config import load_config, project_root
from ai_morning_radar.models import MarketSnapshot
from ai_morning_radar.pipeline import _load_fixture
from ai_morning_radar.scoring import calculate_sentiment, find_anomalies


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.market, _, _ = _load_fixture()

    def test_score_is_weighted_and_bounded(self) -> None:
        score, label, components = calculate_sentiment(self.market, self.config)
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 5)
        self.assertEqual(len(components), 10)
        self.assertIn(label, {"偏多", "明显偏多"})

    def test_missing_components_are_renormalized(self) -> None:
        partial = [item for item in self.market if item.symbol in {"^SOX", "^IXIC"}]
        score, _, components = calculate_sentiment(partial, self.config)
        self.assertGreater(score, 0)
        self.assertTrue(any(item.normalized is None for item in components))

    def test_anomaly_thresholds(self) -> None:
        symbols = {item.symbol for item in find_anomalies(self.market, self.config)}
        self.assertIn("NVDA", symbols)
        self.assertIn("MU", symbols)
        self.assertIn("^SOX", symbols)

    def test_normalization_marks_stale_and_computes_bps(self) -> None:
        now = datetime.now(timezone.utc)
        instrument = {"symbol": "^TNX", "name": "美债", "category": "macro", "change_unit": "bp"}
        item = normalize_snapshot(instrument, [41.4, 41.2], [now - timedelta(days=2), now - timedelta(days=2)], now)
        self.assertEqual(item.status, "stale")
        self.assertAlmostEqual(item.change_bps or 0, -2.0)

    def test_korea_change_uses_prior_close_override(self) -> None:
        now = datetime.now(timezone.utc)
        instrument = {"symbol": "000660.KS", "name": "SK海力士", "category": "korea"}
        item = normalize_snapshot(instrument, [105, 106, 108], [now, now, now], now, previous_close_override=100)
        self.assertAlmostEqual(item.change_pct or 0, 8.0)
        self.assertEqual(item.sparkline, [105.0, 106.0, 108.0])


if __name__ == "__main__":
    unittest.main()
