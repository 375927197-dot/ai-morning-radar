from __future__ import annotations

import re
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from ..models import MacroEvent


BLS_ICS = "https://www.bls.gov/schedule/news_release/bls.ics"
FED_CALENDAR = "https://www.federalreserve.gov/newsevents/calendar.htm"


def _unfold_ics(lines: Iterable[str]) -> list[str]:
    output: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and output:
            output[-1] += line[1:]
        else:
            output.append(line.rstrip())
    return output


def parse_bls_ics(text: str, now: datetime | None = None) -> list[MacroEvent]:
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(days=2)
    blocks = text.replace("\r\n", "\n").split("BEGIN:VEVENT")
    events: list[MacroEvent] = []
    for block in blocks[1:]:
        fields: dict[str, str] = {}
        dtstart_key = ""
        for line in _unfold_ics(block.splitlines()):
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.split(";", 1)[0]] = value
                if key.startswith("DTSTART"):
                    dtstart_key = key
        raw = fields.get("DTSTART", "")
        match = re.search(r"(\d{8})T?(\d{6})?Z?", raw)
        if not match:
            continue
        fmt = "%Y%m%d%H%M%S" if match.group(2) else "%Y%m%d"
        value = match.group(1) + (match.group(2) or "")
        parsed = datetime.strptime(value, fmt)
        if raw.endswith("Z"):
            event_at = parsed.replace(tzinfo=timezone.utc)
        elif "TZID=" in dtstart_key:
            timezone_name = dtstart_key.split("TZID=", 1)[1].split(";", 1)[0]
            event_at = parsed.replace(tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc)
        else:
            event_at = parsed.replace(tzinfo=timezone.utc)
        if now - timedelta(hours=12) <= event_at <= horizon:
            events.append(MacroEvent(
                title=fields.get("SUMMARY", "BLS数据发布").replace("\\,", ","),
                event_at=event_at.isoformat(), source="U.S. BLS", url=fields.get("URL", BLS_ICS),
                importance="高", evidence_id=f"CAL-BLS-{len(events)+1:02d}",
            ))
    return events


def collect_macro_calendar() -> tuple[list[MacroEvent], list[str]]:
    warnings: list[str] = []
    events: list[MacroEvent] = []
    try:
        req = urllib.request.Request(BLS_ICS, headers={"User-Agent": "AI-Morning-Radar/0.1"})
        with urllib.request.urlopen(req, timeout=12) as response:
            events.extend(parse_bls_ics(response.read().decode("utf-8", "replace")))
    except Exception as exc:
        warnings.append(f"BLS日历不可用：{type(exc).__name__}")

    # The Fed page changes markup frequently. Keep the official calendar as a linked
    # evidence source and surface availability; AI/news collection provides event text.
    try:
        req = urllib.request.Request(FED_CALENDAR, headers={"User-Agent": "AI-Morning-Radar/0.1"})
        with urllib.request.urlopen(req, timeout=12) as response:
            body = response.read().decode("utf-8", "replace")
        if any(keyword in body for keyword in ("FOMC", "Speech", "Speeches")):
            events.append(MacroEvent(
                title="查看未来48小时美联储会议、讲话与统计发布",
                event_at=datetime.now(timezone.utc).isoformat(), source="Federal Reserve",
                url=FED_CALENDAR, importance="中", evidence_id="CAL-FED-01",
            ))
    except Exception as exc:
        warnings.append(f"美联储日历不可用：{type(exc).__name__}")
    return events, warnings
