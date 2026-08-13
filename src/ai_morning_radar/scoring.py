from __future__ import annotations

from statistics import mean
from typing import Any

from .models import MarketSnapshot, ScoreComponent, SectorImpact


KEY_SYMBOLS = {
    "sox": "^SOX",
    "nasdaq": "^IXIC",
    "sp500": "^GSPC",
    "hynix": "000660.KS",
    "samsung": "005930.KS",
    "kospi": "^KS11",
    "vix": "^VIX",
    "us10y": "^TNX",
    "dxy": "DX-Y.NYB",
}


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def calculate_sentiment(
    snapshots: list[MarketSnapshot], config: dict[str, Any]
) -> tuple[float, str, list[ScoreComponent]]:
    by_symbol = {item.symbol: item for item in snapshots}
    weights = config["scoring"]["weights"]
    thresholds = config["scoring"]["thresholds"]
    inverse = set(config["scoring"]["inverse"])
    components: list[ScoreComponent] = []

    for key, weight in weights.items():
        evidence: list[str] = []
        value: float | None
        if key == "ai_basket":
            basket = [s for s in snapshots if s.category == "us_ai" and s.change_pct is not None]
            value = mean(s.change_pct for s in basket) if basket else None
            evidence = [s.evidence_id for s in basket]
        else:
            snapshot = by_symbol.get(KEY_SYMBOLS[key])
            if snapshot and key == "us10y":
                value = snapshot.change_bps
            else:
                value = snapshot.change_pct if snapshot else None
            evidence = [snapshot.evidence_id] if snapshot else []
        normalized = None if value is None else _clip(value / float(thresholds[key]))
        if normalized is not None and key in inverse:
            normalized *= -1
        components.append(ScoreComponent(key, value, normalized, float(weight), evidence))

    available_weight = sum(c.weight for c in components if c.normalized is not None)
    weighted = sum((c.normalized or 0) * c.weight for c in components)
    score = round(5 * weighted / available_weight, 2) if available_weight else 0.0
    if score >= 2.5:
        label = "明显偏多"
    elif score >= 0.75:
        label = "偏多"
    elif score <= -2.5:
        label = "明显偏空"
    elif score <= -0.75:
        label = "偏空"
    else:
        label = "中性"
    return score, label, components


def find_anomalies(snapshots: list[MarketSnapshot], config: dict[str, Any]) -> list[MarketSnapshot]:
    thresholds = {
        item["symbol"]: float(item.get("threshold", 3.0))
        for group in config["groups"].values() for item in group
    }
    result: list[MarketSnapshot] = []
    for item in snapshots:
        movement = abs(item.change_bps) if item.change_bps is not None else (
            abs(item.change_pct) if item.change_pct is not None else None
        )
        if movement is not None and movement >= thresholds.get(item.symbol, 3.0):
            result.append(item)
    return sorted(result, key=lambda item: abs(item.change_bps or item.change_pct or 0), reverse=True)


def rule_sector_impacts(snapshots: list[MarketSnapshot], config: dict[str, Any]) -> list[SectorImpact]:
    by_symbol = {item.symbol: item for item in snapshots}
    impacts: list[SectorImpact] = []
    for sector, symbols in config["sector_keywords"].items():
        evidence = [by_symbol[s] for s in symbols if s in by_symbol and by_symbol[s].change_pct is not None]
        signal = mean(item.change_pct for item in evidence) if evidence else 0.0
        if signal >= 0.6:
            direction = "利好"
        elif signal <= -0.6:
            direction = "利空"
        else:
            direction = "中性"
        strength = min(5, max(1, round(abs(signal)) + 1))
        names = "、".join(item.name for item in evidence[:4]) or "外盘有效数据不足"
        impacts.append(SectorImpact(
            sector=sector, direction=direction, strength=strength, horizon="当日集合竞价至早盘",
            reason=f"规则映射：{names}综合变动约{signal:+.2f}%",
            evidence_ids=[item.evidence_id for item in evidence], kind="推断",
        ))
    return impacts

