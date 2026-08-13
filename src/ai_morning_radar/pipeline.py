from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .analysis import analyze
from .collectors.calendar import collect_macro_calendar
from .collectors.market import collect_market
from .collectors.news import collect_news
from .config import all_instruments, load_config, project_root
from .email_sender import send_report
from .models import MacroEvent, MarketSnapshot, MorningReport, NewsItem
from .reporting import write_report
from .scoring import calculate_sentiment


SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(slots=True)
class RunOptions:
    fixture: bool = False
    dry_run: bool = False
    scheduled: bool = False
    config_path: str | None = None


def is_china_trading_day(day: date) -> tuple[bool, str | None]:
    try:
        import exchange_calendars as xcals  # type: ignore
        calendar = xcals.get_calendar("XSHG")
        return bool(calendar.is_session(day.isoformat())), None
    except Exception:
        # Safe fallback for local fixture use; production installs exchange-calendars.
        return day.weekday() < 5, "交易日历不可用，已按周一至周五判断"


def _load_fixture() -> tuple[list[MarketSnapshot], list[NewsItem], list[MacroEvent]]:
    path = project_root() / "tests" / "fixtures" / "morning_fixture.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    market = [MarketSnapshot(**item) for item in raw["market"]]
    news = [NewsItem(**item) for item in raw["news"]]
    events = [MacroEvent(**item) for item in raw["macro_events"]]
    return market, news, events


def _clock(day: date, hhmm: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=SHANGHAI)


def _wait_for_korea(config: dict[str, Any], now: datetime | None = None) -> None:
    now = now or datetime.now(SHANGHAI)
    capture = _clock(now.date(), config["report"]["korea_capture"])
    late = _clock(now.date(), config["report"]["late_start"])
    if now < capture and now < late:
        seconds = max(0, (capture - now).total_seconds())
        print(f"等待至北京时间 {config['report']['korea_capture']} 补采韩国早盘（约{seconds/60:.1f}分钟）", flush=True)
        time.sleep(seconds)


def _build_report(
    market: list[MarketSnapshot], news: list[NewsItem], events: list[MacroEvent],
    config: dict[str, Any], warnings: list[str], force_fallback: bool,
) -> MorningReport:
    now = datetime.now(SHANGHAI)
    score, label, components = calculate_sentiment(market, config)
    summary, points, impacts, mode, analysis_warnings = analyze(
        market, news, events, config, score, label, force_fallback=force_fallback
    )
    warnings.extend(analysis_warnings)
    expected = len(all_instruments(config))
    success = sum(item.price is not None for item in market)
    if expected and success / expected < 0.8:
        warnings.append(f"核心行情成功率{success}/{expected}，低于80%；所有缺失项已标记")
    return MorningReport(
        report_date=now.date().isoformat(), generated_at=now.isoformat(timespec="seconds"),
        title=f"AI早盘雷达｜{now:%Y-%m-%d}", sentiment_score=score, sentiment_label=label,
        score_components=components, market=market, news=news, macro_events=events,
        sector_impacts=impacts, auction_points=points, one_line_summary=summary,
        analysis_mode=mode, warnings=list(dict.fromkeys(warnings)),
    )


def run(options: RunOptions) -> tuple[MorningReport | None, dict[str, Path]]:
    config = load_config(options.config_path)
    now = datetime.now(SHANGHAI)
    trading_day, calendar_warning = is_china_trading_day(now.date())
    if options.scheduled and not trading_day:
        print(f"{now.date()} 不是上交所交易日，跳过晨报。")
        return None, {}

    warnings = [calendar_warning] if calendar_warning else []
    if options.fixture:
        market, news, events = _load_fixture()
        force_fallback = True
    else:
        market = collect_market(config, {"indices", "us_ai", "macro"})
        news, news_warnings = collect_news(config)
        events, event_warnings = collect_macro_calendar()
        warnings.extend(news_warnings + event_warnings)
        if options.scheduled:
            _wait_for_korea(config)
        market.extend(collect_market(config, {"korea"}))
        current = datetime.now(SHANGHAI)
        force_fallback = options.scheduled and current >= _clock(current.date(), config["report"]["ai_deadline"])
        if force_fallback:
            warnings.append("已超过09:10，为保证送达时效强制使用规则模板")

    report = _build_report(market, news, events, config, warnings, force_fallback)
    output_root = Path(config["report"]["output_dir"])
    if not output_root.is_absolute():
        output_root = project_root() / output_root
    paths = write_report(report, output_root)

    if not options.dry_run and not options.fixture:
        push_warnings = send_report(report, paths["html"], config)
        if push_warnings:
            report.warnings.extend(push_warnings)
            paths = write_report(report, output_root)
    print(f"报告已生成：{paths['html']}")
    return report, paths
