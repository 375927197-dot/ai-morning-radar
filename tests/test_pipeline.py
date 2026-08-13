from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from ai_morning_radar.config import load_config
from datetime import date

from ai_morning_radar.pipeline import RunOptions, is_china_trading_day, run


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


if __name__ == "__main__":
    unittest.main()
