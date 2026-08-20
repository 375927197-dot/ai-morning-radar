from __future__ import annotations

import tempfile
import unittest
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ai_morning_radar.config import load_config

from ai_morning_radar.pipeline import RunOptions, _wait_until, is_china_trading_day, run


class PipelineTests(unittest.TestCase):
    def test_china_holiday_and_weekend_are_closed(self) -> None:
        self.assertTrue(is_china_trading_day(date(2026, 8, 13))[0])
        self.assertFalse(is_china_trading_day(date(2026, 10, 1))[0])
        self.assertFalse(is_china_trading_day(date(2026, 8, 15))[0])

    def test_fixture_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            config = load_config()
            config["report"]["output_dir"] = folder
            config_path = Path(folder) / "config.yaml"
            config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            report, paths = run(RunOptions(fixture=True, dry_run=True, config_path=str(config_path)))
            self.assertIsNotNone(report)
            self.assertEqual(report.analysis_mode, "规则模板")
            self.assertTrue(paths["html"].exists())
            self.assertTrue(paths["json"].exists())

    @patch("ai_morning_radar.pipeline.time.sleep")
    def test_scheduled_waits_until_capture_time(self, sleep) -> None:
        config = load_config()
        now = datetime(2026, 8, 20, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        _wait_until(config, "korea_capture", "采集盘前数据", now)
        sleep.assert_called_once_with(20 * 60)

    @patch("ai_morning_radar.pipeline.time.sleep")
    def test_late_schedule_skips_wait(self, sleep) -> None:
        config = load_config()
        now = datetime(2026, 8, 20, 8, 31, tzinfo=ZoneInfo("Asia/Shanghai"))
        _wait_until(config, "send_time", "发送晨报", now)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
