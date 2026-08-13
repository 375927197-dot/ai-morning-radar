from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .models import MorningReport
from .scoring import find_anomalies


def _safe_error(exc: Exception) -> str:
    return re.sub(r"key=[A-Za-z0-9_-]+", "key=***", str(exc))[:240]


def _post_json(url: str, payload: dict, attempts: int = 3) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("errcode", 0) != 0:
                raise RuntimeError(f"企业微信错误 {result.get('errcode')}: {result.get('errmsg')}")
            return result
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(_safe_error(last or RuntimeError("未知错误")))


def build_summary(report: MorningReport, config: dict) -> str:
    anomalies = find_anomalies(report.market, config)[:5]
    anomaly_text = "\n".join(
        f"> {item.name}：{(item.change_bps if item.change_bps is not None else item.change_pct):+.2f}{'bp' if item.change_bps is not None else '%'}"
        for item in anomalies
    ) or "> 暂无越过预设阈值的异动"
    sectors = "、".join(f"{item.sector}{item.direction}{item.strength}/5" for item in report.sector_impacts if item.direction != "中性") or "七个方向整体中性"
    content = (
        f"# AI早盘雷达｜{report.report_date}\n"
        f"**情绪：{report.sentiment_score:+.2f}/5（{report.sentiment_label}）**\n"
        f"> {report.one_line_summary}\n\n**重点异动**\n{anomaly_text}\n\n"
        f"**A股映射**\n{sectors}\n\n**09:15观察**\n" + "\n".join(f"- {p}" for p in report.auction_points[:3]) +
        f"\n\n<font color=\"comment\">{report.analysis_mode}｜免费行情可能延迟｜不构成投资建议</font>"
    )
    return content[:3900]


def _upload_file(webhook: str, path: Path, attempts: int = 3) -> str:
    key = urllib.parse.parse_qs(urllib.parse.urlparse(webhook).query).get("key", [""])[0]
    if not key:
        raise ValueError("企业微信Webhook缺少key参数")
    upload_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={key}&type=file"
    boundary = "----Radar" + uuid.uuid4().hex
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"{path.name}\"\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(upload_url, data=body, method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("errcode", 0) != 0 or not result.get("media_id"):
                raise RuntimeError(f"文件上传失败 {result.get('errcode')}: {result.get('errmsg')}")
            return str(result["media_id"])
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(_safe_error(last or RuntimeError("未知错误")))


def send_report(report: MorningReport, html_path: Path, config: dict) -> list[str]:
    webhook = os.getenv("WECOM_WEBHOOK_URL")
    if not webhook:
        return ["未配置WECOM_WEBHOOK_URL，已跳过企业微信推送"]
    warnings: list[str] = []
    try:
        _post_json(webhook, {"msgtype": "markdown", "markdown": {"content": build_summary(report, config)}})
    except Exception as exc:
        warnings.append(f"企业微信摘要发送失败：{_safe_error(exc)}")
    try:
        media_id = _upload_file(webhook, html_path)
        _post_json(webhook, {"msgtype": "file", "file": {"media_id": media_id}})
    except Exception as exc:
        warnings.append(f"企业微信HTML发送失败：{_safe_error(exc)}")
    return warnings


def notify_failure(message: str) -> bool:
    webhook = os.getenv("WECOM_WEBHOOK_URL")
    if not webhook:
        return False
    _post_json(webhook, {"msgtype": "text", "text": {"content": f"AI早盘雷达运行失败：{message[:500]}"}})
    return True
