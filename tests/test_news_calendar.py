from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ai_morning_radar.collectors.calendar import parse_bls_ics
from ai_morning_radar.collectors.news import deduplicate, is_relevant
from ai_morning_radar.models import NewsItem


class FeedTests(unittest.TestCase):
    def test_news_deduplication(self) -> None:
        items = [
            NewsItem("NVIDIA launches AI chip", "A", "2026-08-13T01:00:00+00:00", "https://a"),
            NewsItem("NVIDIA launches AI chip!", "B", "2026-08-13T00:00:00+00:00", "https://b"),
        ]
        result = deduplicate(items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].evidence_id, "NEWS-001")

    def test_marketing_soft_news_is_filtered(self) -> None:
        soft = NewsItem("NVIDIA CEO tops Glassdoor list", "A", "2026-08-13T01:00:00+00:00", "https://a", "AI company careers")
        material = NewsItem("Micron expands HBM memory output", "A", "2026-08-13T01:00:00+00:00", "https://b", "Semiconductor demand")
        self.assertFalse(is_relevant(soft))
        self.assertTrue(is_relevant(material))

    def test_bls_ics_parsing(self) -> None:
        text = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20260813T123000Z\nSUMMARY:Consumer Price Index\nURL:https://bls.gov/cpi\nEND:VEVENT\nEND:VCALENDAR"
        now = datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc)
        result = parse_bls_ics(text, now)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].importance, "高")


if __name__ == "__main__":
    unittest.main()
