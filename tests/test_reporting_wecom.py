from __future__ import annotations

import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch
from pathlib import Path

from ai_morning_radar.analysis import fallback_analysis
from ai_morning_radar.config import load_config
from ai_morning_radar.models import MorningReport
from ai_morning_radar.pipeline import _load_fixture
from ai_morning_radar.reporting import render_html, write_report
from ai_morning_radar.scoring import calculate_sentiment
from ai_morning_radar.wecom import _post_json, _safe_error, _upload_file, build_summary


class ReportingTests(unittest.TestCase):
    def _report(self) -> tuple[MorningReport, dict]:
        config = load_config()
        market, news, events = _load_fixture()
        score, label, components = calculate_sentiment(market, config)
        summary, points, impacts, mode = fallback_analysis(market, config, score, label)
        report = MorningReport("2026-08-13", "2026-08-13T09:00:00+08:00", "AI早盘雷达｜测试", score, label, components, market, news, events, impacts, points, summary, mode)
        return report, config

    def test_outputs_and_self_contained_html(self) -> None:
        report, _ = self._report()
        with tempfile.TemporaryDirectory() as folder:
            paths = write_report(report, folder)
            self.assertTrue(all(path.exists() for path in paths.values()))
            content = paths["html"].read_text(encoding="utf-8")
            self.assertIn("<style>", content)
            self.assertNotIn("<link", content)
            self.assertIn("市场雷达", content)

    def test_wecom_summary_within_limit(self) -> None:
        report, config = self._report()
        summary = build_summary(report, config)
        self.assertLessEqual(len(summary), 3900)
        self.assertIn("09:15观察", summary)

    @patch("ai_morning_radar.wecom.time.sleep")
    @patch("ai_morning_radar.wecom.urllib.request.urlopen")
    def test_wecom_retries_three_times(self, urlopen, _sleep) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"errcode":0,"errmsg":"ok"}'
        urlopen.side_effect = [urllib.error.URLError("one"), urllib.error.URLError("two"), response]
        result = _post_json("https://example.com/webhook?key=secret", {"msgtype": "text"})
        self.assertEqual(result["errcode"], 0)
        self.assertEqual(urlopen.call_count, 3)

    def test_secret_is_redacted_from_error(self) -> None:
        value = _safe_error(RuntimeError("failed https://x.test/?key=very-secret-token"))
        self.assertNotIn("very-secret-token", value)
        self.assertIn("key=***", value)

    @patch("ai_morning_radar.wecom.time.sleep")
    @patch("ai_morning_radar.wecom.urllib.request.urlopen")
    def test_file_upload_retries(self, urlopen, _sleep) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"errcode":0,"media_id":"media-1"}'
        urlopen.side_effect = [urllib.error.URLError("one"), response]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.html"
            path.write_text("ok", encoding="utf-8")
            media_id = _upload_file("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret", path)
        self.assertEqual(media_id, "media-1")
        self.assertEqual(urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
