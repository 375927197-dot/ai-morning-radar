from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Iterable

from .models import MarketSnapshot, MorningReport


def _fmt_change(item: MarketSnapshot) -> str:
    if item.change_bps is not None:
        return f"{item.change_bps:+.1f}bp"
    if item.change_pct is not None:
        return f"{item.change_pct:+.2f}%"
    return "--"


def _sparkline(values: list[float]) -> str:
    if len(values) < 2:
        return ""
    width, height, pad = 100, 26, 2
    low, high = min(values), max(values)
    span = high - low or 1
    points = " ".join(
        f"{pad + i * (width - 2 * pad) / (len(values)-1):.1f},{height-pad-(v-low)*(height-2*pad)/span:.1f}"
        for i, v in enumerate(values)
    )
    color = "#ef4444" if values[-1] >= values[0] else "#22c55e"
    return f'<svg class="spark" viewBox="0 0 {width} {height}" aria-label="走势图"><polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/></svg>'


def render_markdown(report: MorningReport) -> str:
    lines = [
        f"# {report.title}", "",
        f"> 生成时间：{report.generated_at}｜分析模式：{report.analysis_mode}", "",
        f"## 情绪评分：{report.sentiment_score:+.2f}/5（{report.sentiment_label}）", "",
        report.one_line_summary, "", "## 隔夜指数与重点公司", "",
        "| 市场 | 标的 | 价格 | 变动 | 数据时间 | 状态 |", "|---|---|---:|---:|---|---|",
    ]
    category_names = {"indices": "指数", "us_ai": "美股AI", "korea": "韩国", "macro": "宏观"}
    for item in report.market:
        price = "--" if item.price is None else f"{item.price:,.2f}"
        lines.append(f"| {category_names.get(item.category,item.category)} | {item.name} `{item.symbol}` | {price} | {_fmt_change(item)} | {item.as_of} | {item.status} |")
    lines.extend(["", "## AI重大新闻", ""])
    lines.extend([f"- [{n.title}]({n.url}) — {n.source}，{n.published_at}（证据 `{n.evidence_id}`）" for n in report.news] or ["- 最近36小时未获得有效新闻。"])
    lines.extend(["", "## 宏观风险日历", ""])
    lines.extend([f"- **{e.importance}** [{e.title}]({e.url}) — {e.event_at}（`{e.evidence_id}`）" for e in report.macro_events] or ["- 未来48小时未获得有效事件。"])
    lines.extend(["", "## 对A股 AI 科技方向的影响", "", "| 方向 | 判断 | 强度 | 时效 | 依据 |", "|---|---|---:|---|---|"])
    for impact in report.sector_impacts:
        refs = ", ".join(f"`{v}`" for v in impact.evidence_ids) or "数据不足"
        lines.append(f"| {impact.sector} | {impact.direction}（{impact.kind}） | {impact.strength}/5 | {impact.horizon} | {impact.reason} [{refs}] |")
    lines.extend(["", "## 集合竞价观察点", ""])
    lines.extend(f"- {point}" for point in report.auction_points)
    if report.warnings:
        lines.extend(["", "## 数据状态", ""] + [f"- {warning}" for warning in report.warnings])
    lines.extend(["", "---", "", report.disclaimer, ""])
    return "\n".join(lines)


def _market_rows(items: Iterable[MarketSnapshot]) -> str:
    rows: list[str] = []
    for item in items:
        value = item.change_bps if item.change_bps is not None else item.change_pct
        cls = "up" if (value or 0) > 0 else ("down" if (value or 0) < 0 else "flat")
        price = "--" if item.price is None else f"{item.price:,.2f}"
        rows.append(
            f'<tr data-text="{html.escape((item.name+item.symbol).lower())}"><td><b>{html.escape(item.name)}</b><small>{html.escape(item.symbol)}</small></td>'
            f'<td>{price}</td><td class="{cls}">{_fmt_change(item)}</td><td>{_sparkline(item.sparkline)}</td>'
            f'<td><span class="status {html.escape(item.status)}">{html.escape(item.status)}</span><small>{html.escape(item.as_of)}</small></td></tr>'
        )
    return "".join(rows)


def render_html(report: MorningReport) -> str:
    news = "".join(f'<li><a href="{html.escape(n.url)}">{html.escape(n.title)}</a><span>{html.escape(n.source)} · {html.escape(n.published_at)} · {n.evidence_id}</span></li>' for n in report.news) or "<li>最近36小时未获得有效新闻。</li>"
    events = "".join(f'<li><b>{html.escape(e.importance)}</b> <a href="{html.escape(e.url)}">{html.escape(e.title)}</a><span>{html.escape(e.event_at)} · {e.evidence_id}</span></li>' for e in report.macro_events) or "<li>未来48小时未获得有效事件。</li>"
    impacts = "".join(
        f'<article class="impact"><div><h3>{html.escape(i.sector)}</h3><span class="pill {"good" if i.direction=="利好" else "bad" if i.direction=="利空" else "neutral"}">{i.direction} · {i.strength}/5</span></div><p>{html.escape(i.reason)}</p><small>{html.escape(i.kind)} · {html.escape(i.horizon)} · {html.escape(", ".join(i.evidence_ids) or "数据不足")}</small></article>'
        for i in report.sector_impacts
    )
    warnings = "".join(f"<li>{html.escape(v)}</li>" for v in report.warnings)
    score_pct = max(0, min(100, (report.sentiment_score + 5) * 10))
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(report.title)}</title>
<style>
:root{{--bg:#07111f;--panel:#0f1d2e;--line:#23364b;--text:#e8f0f8;--muted:#91a4b7;--red:#ff5b63;--green:#2dd4a7;--blue:#53a7ff}}*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 10% 0,#142b45,var(--bg) 38%);color:var(--text);font-family:Inter,"Microsoft YaHei",sans-serif}}main{{max-width:1100px;margin:auto;padding:28px 18px 60px}}header{{display:flex;justify-content:space-between;gap:20px;align-items:end;border-bottom:1px solid var(--line);padding-bottom:20px}}h1{{margin:0;font-size:clamp(28px,5vw,52px)}}h2{{margin-top:34px}}small,.muted,li span{{display:block;color:var(--muted);font-size:12px;margin-top:5px}}.hero{{display:grid;grid-template-columns:220px 1fr;gap:18px;margin-top:22px}}.card,.impact{{background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:14px;padding:18px}}.score{{font-size:42px;font-weight:800}}.meter{{height:8px;background:#17283a;border-radius:10px;margin-top:14px;overflow:hidden}}.meter i{{display:block;height:100%;width:{score_pct}%;background:linear-gradient(90deg,var(--green),#ffd166,var(--red))}}input{{width:100%;background:#0a1624;border:1px solid var(--line);border-radius:10px;color:var(--text);padding:11px 14px;margin:8px 0 12px}}table{{width:100%;border-collapse:collapse;background:var(--panel);border-radius:14px;overflow:hidden}}th,td{{text-align:left;padding:12px;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-size:12px}}td:nth-child(2),td:nth-child(3){{text-align:right}}.up{{color:var(--red);font-weight:700}}.down{{color:var(--green);font-weight:700}}.spark{{width:100px;height:26px}}.status{{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:2px 7px;font-size:11px}}.status.ok{{color:var(--green)}}.status.missing,.status.error{{color:var(--red)}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.impact>div{{display:flex;align-items:center;justify-content:space-between;gap:8px}}.impact h3{{margin:0}}.impact p{{line-height:1.7}}.pill{{border-radius:99px;padding:5px 9px;font-size:12px;white-space:nowrap}}.good{{background:#3c1720;color:#ff9ea3}}.bad{{background:#12392f;color:#74e2c4}}.neutral{{background:#263545;color:#c8d5e2}}ul{{padding-left:22px}}li{{margin:10px 0;line-height:1.55}}a{{color:#7ebdff}}footer{{margin-top:40px;color:var(--muted);font-size:12px}}@media(max-width:700px){{.hero,.grid{{grid-template-columns:1fr}}header{{display:block}}table{{font-size:12px}}th:nth-child(4),td:nth-child(4){{display:none}}}}
</style></head><body><main><header><div><div class="muted">A股 AI 科技 · 盘前研究</div><h1>{html.escape(report.title)}</h1></div><div class="muted">{html.escape(report.generated_at)}<br>{html.escape(report.analysis_mode)}</div></header>
<section class="hero"><div class="card"><div class="muted">外盘情绪</div><div class="score">{report.sentiment_score:+.2f}</div><b>{html.escape(report.sentiment_label)}</b><div class="meter"><i></i></div></div><div class="card"><div class="muted">一句话结论</div><h2>{html.escape(report.one_line_summary)}</h2></div></section>
<h2>市场雷达</h2><input id="filter" placeholder="搜索标的或代码…"><table id="market"><thead><tr><th>标的</th><th>价格</th><th>变动</th><th>走势</th><th>数据状态</th></tr></thead><tbody>{_market_rows(report.market)}</tbody></table>
<h2>AI重大新闻</h2><div class="card"><ul>{news}</ul></div><h2>宏观风险日历</h2><div class="card"><ul>{events}</ul></div>
<h2>A股方向映射</h2><section class="grid">{impacts}</section><h2>集合竞价观察点</h2><div class="card"><ol>{''.join(f'<li>{html.escape(p)}</li>' for p in report.auction_points)}</ol></div>
{f'<h2>数据状态</h2><div class="card"><ul>{warnings}</ul></div>' if warnings else ''}<footer>{html.escape(report.disclaimer)}</footer></main>
<script>document.getElementById('filter').addEventListener('input',e=>{{const q=e.target.value.toLowerCase();document.querySelectorAll('#market tbody tr').forEach(r=>r.hidden=!r.dataset.text.includes(q))}})</script></body></html>'''


def write_report(report: MorningReport, output_root: str | Path) -> dict[str, Path]:
    folder = Path(output_root) / report.report_date
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"ai-morning-radar-{report.report_date}"
    paths = {"markdown": folder / f"{stem}.md", "html": folder / f"{stem}.html", "json": folder / f"{stem}.json"}
    paths["markdown"].write_text(render_markdown(report), encoding="utf-8")
    paths["html"].write_text(render_html(report), encoding="utf-8")
    paths["json"].write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return paths

