from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Direction = Literal["利好", "利空", "中性"]


@dataclass(slots=True)
class MarketSnapshot:
    symbol: str
    name: str
    category: str
    price: float | None
    change_pct: float | None
    previous_close: float | None
    as_of: str
    source: str = "Yahoo Finance / yfinance"
    session: str = "最近交易时段"
    status: str = "ok"
    stale_minutes: int | None = None
    change_bps: float | None = None
    sparkline: list[float] = field(default_factory=list)
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NewsItem:
    title: str
    source: str
    published_at: str
    url: str
    summary: str = ""
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MacroEvent:
    title: str
    event_at: str
    source: str
    url: str
    importance: str = "中"
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SectorImpact:
    sector: str
    direction: Direction
    strength: int
    horizon: str
    reason: str
    evidence_ids: list[str]
    kind: str = "推断"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScoreComponent:
    key: str
    value: float | None
    normalized: float | None
    weight: float
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MorningReport:
    report_date: str
    generated_at: str
    title: str
    sentiment_score: float
    sentiment_label: str
    score_components: list[ScoreComponent]
    market: list[MarketSnapshot]
    news: list[NewsItem]
    macro_events: list[MacroEvent]
    sector_impacts: list[SectorImpact]
    auction_points: list[str]
    one_line_summary: str
    analysis_mode: str
    warnings: list[str] = field(default_factory=list)
    disclaimer: str = "仅用于盘前信息整理和风险观察，不构成投资建议。免费行情可能延迟或缺失。"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

