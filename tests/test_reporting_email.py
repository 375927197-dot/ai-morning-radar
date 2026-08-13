from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_morning_radar.analysis import fallback_analysis
from ai_morning_radar.config import load_config
from ai_morning_radar.email_sender import (
    EmailSettings,
    _load_settings,
    _safe_error,
    _send_email,
    build_message,
    build_summary,
    send_report,
)
from ai_morning_radar.models import MorningReport
from ai_morning_radar.pipeline import _load_fixture
from ai_morning_radar.reporting import write_report
from ai_morning_radar.scoring import calculate_sentiment


class ReportingEmailTests(unittest.TestCase):
    def _report(self) -> tuple[MorningReport, dict]:
        config = load_config()
        market, news, events = _load_fixture()
        score, label, components = calculate_sentiment(market, config)
        summary, points, impacts, mode = fallback_analysis(market, config, score, label)
        report = MorningReport(
            "2026-08-13",
            "2026-08-13T09:00:00+08:00",
            "AI早盘雷达｜测试",
            score,
            label,
            components,
            market,
            news,
            events,
            impacts,
            points,
            summary,
            mode,
        )
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

    def test_email_contains_summary_html_and_attachment(self) -> None:
        report, config = self._report()
        settings = EmailSettings("123456@qq.com", "secret", ("123456@qq.com",))
        with tempfile.TemporaryDirectory() as folder:
            paths = write_report(report, folder)
            message = build_message(report, paths["html"], config, settings)
        self.assertIn("AI早盘雷达", message["Subject"])
        self.assertIn("09:15观察", build_summary(report, config))
        self.assertEqual(len(list(message.iter_attachments())), 1)
        self.assertGreaterEqual(
            sum(part.get_content_type() == "text/html" for part in message.walk()),
            2,
        )

    @patch("ai_morning_radar.email_sender.time.sleep")
    @patch("ai_morning_radar.email_sender.smtplib.SMTP_SSL")
    def test_email_retries_three_times(self, smtp_ssl, _sleep) -> None:
        server = MagicMock()
        connection = MagicMock()
        connection.__enter__.return_value = server
        smtp_ssl.side_effect = [OSError("one"), OSError("two"), connection]
        settings = EmailSettings("123456@qq.com", "secret", ("123456@qq.com",))
        report, config = self._report()
        with tempfile.TemporaryDirectory() as folder:
            paths = write_report(report, folder)
            message = build_message(report, paths["html"], config, settings)
            _send_email(message, settings)
        self.assertEqual(smtp_ssl.call_count, 3)
        server.login.assert_called_once_with("123456@qq.com", "secret")
        server.send_message.assert_called_once()

    def test_missing_email_configuration_skips_send(self) -> None:
        report, config = self._report()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            paths = write_report(report, folder)
            warnings = send_report(report, paths["html"], config)
        self.assertIn("已跳过邮件推送", warnings[0])

    def test_recipient_defaults_to_sender(self) -> None:
        with patch.dict(
            os.environ,
            {"QQ_EMAIL_ADDRESS": "123456@qq.com", "QQ_EMAIL_AUTH_CODE": "secret"},
            clear=True,
        ):
            settings = _load_settings()
        self.assertIsNotNone(settings)
        self.assertEqual(settings.recipients, ("123456@qq.com",))

    def test_secret_is_redacted_from_error(self) -> None:
        value = _safe_error(RuntimeError("failed auth_code=very-secret-token"))
        self.assertNotIn("very-secret-token", value)
        self.assertIn("auth_code=***", value)


if __name__ == "__main__":
    unittest.main()
