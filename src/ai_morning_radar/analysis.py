from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Any

from .models import MacroEvent, MarketSnapshot, NewsItem, SectorImpact
from .scoring import find_anomalies, rule_sector_impacts


SECTORS = ["存储/HBM", "半导体设备材料", "服务器与算力", "CPO/光模块", "PCB/铜连接", "液冷", "机器人"]


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "one_line_summary": {"type": "string"},
        "auction_points": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6},
        "sector_impacts": {
            "type": "array", "minItems": 7, "maxItems": 7,
            "items": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "enum": SECTORS},
                    "direction": {"type": "string", "enum": ["利好", "利空", "中性"]},
                    "strength": {"type": "integer", "minimum": 1, "maximum": 5},
                    "horizon": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "kind": {"type": "string", "enum": ["事实", "推断"]},
                },
                "required": ["sector", "direction", "strength", "horizon", "reason", "evidence_ids", "kind"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["one_line_summary", "auction_points", "sector_impacts"],
    "additionalProperties": False,
}


def fallback_analysis(
    snapshots: list[MarketSnapshot], config: dict[str, Any], score: float, label: str
) -> tuple[str, list[str], list[SectorImpact], str]:
    anomalies = find_anomalies(snapshots, config)
    highlights = [
        f"{item.name}{(item.change_bps if item.change_bps is not None else item.change_pct):+.2f}{'bp' if item.change_bps is not None else '%'}"
        for item in anomalies[:3]
    ]
    suffix = "，重点异动：" + "、".join(highlights) if highlights else "，暂无越过预设阈值的异动"
    summary = f"外盘AI科技情绪{label}（{score:+.2f}/5）{suffix}。"
    points = [
        "09:15先观察存储、算力和光模块方向竞价强弱是否与外盘信号一致。",
        "若高开但量能与板块联动不足，谨防外盘信息已被提前交易。",
        "关注美元、美债收益率和VIX是否共同指向风险偏好变化。",
    ]
    return summary, points, rule_sector_impacts(snapshots, config), "规则模板"


def _extract_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise ValueError("Responses API未返回output_text")


def _validate_ai(data: dict[str, Any], valid_evidence: set[str]) -> tuple[str, list[str], list[SectorImpact]]:
    if set(data) != {"one_line_summary", "auction_points", "sector_impacts"}:
        raise ValueError("AI输出字段不完整")
    if len(data["sector_impacts"]) != 7:
        raise ValueError("AI未覆盖全部七个方向")
    impacts: list[SectorImpact] = []
    seen: set[str] = set()
    for raw in data["sector_impacts"]:
        unknown = set(raw["evidence_ids"]) - valid_evidence
        if unknown:
            raise ValueError(f"AI引用了不存在的证据：{sorted(unknown)}")
        if any(char.isdigit() for char in raw["reason"]) and not raw["evidence_ids"]:
            raise ValueError("AI给出了无证据来源的数字")
        if raw["sector"] not in SECTORS or raw["sector"] in seen:
            raise ValueError("AI方向重复或不合法")
        seen.add(raw["sector"])
        impacts.append(SectorImpact(**raw))
    return str(data["one_line_summary"]), [str(v) for v in data["auction_points"]], impacts


def analyze(
    snapshots: list[MarketSnapshot], news: list[NewsItem], events: list[MacroEvent],
    config: dict[str, Any], score: float, label: str, force_fallback: bool = False,
) -> tuple[str, list[str], list[SectorImpact], str, list[str]]:
    warnings: list[str] = []
    api_key = os.getenv("OPENAI_API_KEY")
    if force_fallback or not api_key:
        if not api_key and not force_fallback:
            warnings.append("未配置OPENAI_API_KEY，已使用规则模板")
        return (*fallback_analysis(snapshots, config, score, label), warnings)

    valid_evidence = {item.evidence_id for item in [*snapshots, *news, *events] if item.evidence_id}
    evidence = {
        "sentiment": {"score": score, "label": label, "immutable": True},
        "market": [asdict(item) for item in snapshots if item.status != "error"],
        "news": [asdict(item) for item in news],
        "macro_events": [asdict(item) for item in events],
    }
    prompt = (
        "你是A股AI科技盘前研究助手。只能依据给定证据解释，不得改写行情或情绪分数，"
        "不得给出个股买卖指令。每个reason要明确是事实还是推断，所有可验证结论必须引用evidence_ids。"
        "从A股集合竞价视角覆盖七个固定方向，输出简洁中文。\n证据："
        + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    )
    body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        "input": [{"role": "user", "content": prompt}],
        "reasoning": {"effort": "low"},
        "text": {"format": {"type": "json_schema", "name": "morning_radar_analysis", "schema": ANALYSIS_SCHEMA, "strict": True}},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parsed = json.loads(_extract_output_text(payload))
        summary, points, impacts = _validate_ai(parsed, valid_evidence)
        return summary, points, impacts, f"OpenAI {body['model']}", warnings
    except Exception as exc:
        warnings.append(f"AI分析失败，已使用规则模板：{type(exc).__name__}")
        return (*fallback_analysis(snapshots, config, score, label), warnings)
