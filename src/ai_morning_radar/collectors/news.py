from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable

from ..models import NewsItem


TAG_RE = re.compile(r"<[^>]+>")
RELEVANT_RE = re.compile(
    r"\b(ai|artificial intelligence|gpu|semiconductor|chip|memory|hbm|data ?center|cloud|"
    r"nvidia|amd|micron|openai|anthropic|deepmind|gemini|xai|large language model|robot)\b",
    re.IGNORECASE,
)
LOW_VALUE_RE = re.compile(
    r"glassdoor|best ceo|careers?|back.to.school|cloud gaming|pixel watch|pixel buds|accessor(?:y|ies)|"
    r"biggest analyst calls|generational buying|i.?m buying|what .* mean for .* investors",
    re.IGNORECASE,
)
TRUSTED_NEWS_RE = re.compile(
    r"Reuters|Bloomberg|CNBC|Yahoo Finance|Financial Times|Wall Street Journal|The Verge|"
    r"TechCrunch|Nikkei Asia|Yonhap|Korea (?:Herald|Times)|Associated Press|BBC|Fortune",
    re.IGNORECASE,
)


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return html.unescape(TAG_RE.sub(" ", element.text)).strip()


def _published(value: str) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)


def deduplicate(items: Iterable[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    result: list[NewsItem] = []
    for item in sorted(items, key=lambda x: x.published_at, reverse=True):
        key = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", item.title.lower())[:100]
        if not key or key in seen:
            continue
        seen.add(key)
        item.evidence_id = f"NEWS-{len(result) + 1:03d}"
        result.append(item)
    return result


def is_relevant(item: NewsItem) -> bool:
    text = f"{item.title} {item.summary}"
    return bool(RELEVANT_RE.search(text)) and not LOW_VALUE_RE.search(text)


def parse_feed(xml_data: bytes, source: str, cutoff: datetime) -> list[NewsItem]:
    root = ET.fromstring(xml_data)
    entries = root.findall(".//item")
    if not entries:
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    result: list[NewsItem] = []
    for entry in entries:
        title = _text(entry.find("title")) or _text(entry.find("{http://www.w3.org/2005/Atom}title"))
        link_el = entry.find("link")
        if link_el is None:
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
        url = (link_el.get("href") if link_el is not None else None) or _text(link_el)
        date_text = (_text(entry.find("pubDate")) or _text(entry.find("published"))
                     or _text(entry.find("{http://www.w3.org/2005/Atom}published"))
                     or _text(entry.find("{http://www.w3.org/2005/Atom}updated")))
        published = _published(date_text)
        if published < cutoff:
            continue
        summary = (_text(entry.find("description")) or _text(entry.find("summary"))
                   or _text(entry.find("{http://www.w3.org/2005/Atom}summary")))
        publisher = _text(entry.find("source"))
        if source.startswith("Google News") and publisher and not TRUSTED_NEWS_RE.search(publisher):
            continue
        if title and url:
            result.append(NewsItem(title, publisher or source, published.isoformat(), url, summary[:500]))
    return result


def collect_news(config: dict[str, Any]) -> tuple[list[NewsItem], list[str]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=int(config["report"]["news_hours"]))
    items: list[NewsItem] = []
    warnings: list[str] = []
    for feed in config.get("news_feeds", []):
        try:
            request = urllib.request.Request(feed["url"], headers={"User-Agent": "AI-Morning-Radar/0.1"})
            with urllib.request.urlopen(request, timeout=12) as response:
                items.extend(parse_feed(response.read(), feed["name"], cutoff))
        except Exception as exc:
            warnings.append(f"新闻源 {feed['name']} 不可用：{type(exc).__name__}")
    relevant = [item for item in deduplicate(items) if is_relevant(item)]
    # Prevent a busy corporate feed from drowning out all other sources.
    per_source: dict[str, int] = {}
    limited: list[NewsItem] = []
    for item in relevant:
        if per_source.get(item.source, 0) >= 6:
            continue
        per_source[item.source] = per_source.get(item.source, 0) + 1
        item.evidence_id = f"NEWS-{len(limited) + 1:03d}"
        limited.append(item)
        if len(limited) >= 15:
            break
    return limited, warnings
