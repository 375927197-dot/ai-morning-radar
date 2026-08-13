from __future__ import annotations

import os
import re
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from .models import MorningReport
from .scoring import find_anomalies


@dataclass(frozen=True, slots=True)
class EmailSettings:
    sender: str
    auth_code: str
    recipients: tuple[str, ...]
    host: str = "smtp.qq.com"
    port: int = 465


def _safe_error(exc: Exception, secrets: tuple[str, ...] = ()) -> str:
    message = str(exc)
    for secret in secrets:
        if secret:
            message = message.replace(secret, "***")
    message = re.sub(r"(?i)(password|auth_code)=\S+", r"\1=***", message)
    return message[:240]


def _load_settings() -> EmailSettings | None:
    sender = os.getenv("QQ_EMAIL_ADDRESS", "").strip()
    auth_code = os.getenv("QQ_EMAIL_AUTH_CODE", "").strip()
    if not sender or not auth_code:
        return None
    raw_recipients = os.getenv("EMAIL_TO", sender)
    recipients = tuple(item.strip() for item in re.split(r"[,;]", raw_recipients) if item.strip())
    if not recipients:
        recipients = (sender,)
    return EmailSettings(
        sender=sender,
        auth_code=auth_code,
        recipients=recipients,
        host=os.getenv("SMTP_HOST", "smtp.qq.com").strip() or "smtp.qq.com",
        port=int(os.getenv("SMTP_PORT", "465")),
    )


def build_summary(report: MorningReport, config: dict) -> str:
    anomalies = find_anomalies(report.market, config)[:5]
    anomaly_text = "\n".join(
        f"- {item.name}：{(item.change_bps if item.change_bps is not None else item.change_pct):+.2f}"
        f"{'bp' if item.change_bps is not None else '%'}"
        for item in anomalies
    ) or "- 暂无越过预设阈值的异动"
    sectors = "、".join(
        f"{item.sector}{item.direction}{item.strength}/5"
        for item in report.sector_impacts
        if item.direction != "中性"
    ) or "七个方向整体中性"
    auction_points = "\n".join(f"- {point}" for point in report.auction_points[:3])
    return (
        f"AI早盘雷达｜{report.report_date}\n"
        f"情绪：{report.sentiment_score:+.2f}/5（{report.sentiment_label}）\n"
        f"{report.one_line_summary}\n\n"
        f"重点异动\n{anomaly_text}\n\n"
        f"A股映射\n{sectors}\n\n"
        f"09:15观察\n{auction_points}\n\n"
        f"{report.analysis_mode}｜免费行情可能延迟｜不构成投资建议"
    )


def build_message(
    report: MorningReport,
    html_path: Path,
    config: dict,
    settings: EmailSettings,
) -> EmailMessage:
    html = html_path.read_text(encoding="utf-8")
    message = EmailMessage()
    message["From"] = formataddr(("AI早盘雷达", settings.sender))
    message["To"] = ", ".join(settings.recipients)
    message["Subject"] = f"AI早盘雷达｜{report.report_date}｜情绪 {report.sentiment_score:+.2f}/5"
    message.set_content(build_summary(report, config))
    message.add_alternative(html, subtype="html")
    message.add_attachment(
        html.encode("utf-8"),
        maintype="text",
        subtype="html",
        filename=html_path.name,
    )
    return message


def _send_email(message: EmailMessage, settings: EmailSettings, attempts: int = 3) -> None:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.host,
                settings.port,
                timeout=30,
                context=context,
            ) as server:
                server.login(settings.sender, settings.auth_code)
                server.send_message(message)
            return
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(2**attempt)
    raise RuntimeError(_safe_error(last or RuntimeError("未知错误"), (settings.auth_code,)))


def send_report(report: MorningReport, html_path: Path, config: dict) -> list[str]:
    try:
        settings = _load_settings()
    except Exception as exc:
        return [f"QQ邮箱配置无效：{_safe_error(exc)}"]
    if not settings:
        return ["未配置QQ_EMAIL_ADDRESS或QQ_EMAIL_AUTH_CODE，已跳过邮件推送"]
    try:
        _send_email(build_message(report, html_path, config, settings), settings)
    except Exception as exc:
        return [f"QQ邮箱晨报发送失败：{_safe_error(exc, (settings.auth_code,))}"]
    return []


def notify_failure(message: str) -> bool:
    settings = _load_settings()
    if not settings:
        return False
    email = EmailMessage()
    email["From"] = formataddr(("AI早盘雷达", settings.sender))
    email["To"] = ", ".join(settings.recipients)
    email["Subject"] = "AI早盘雷达运行失败"
    email.set_content(f"AI早盘雷达运行失败：\n\n{message[:1000]}")
    _send_email(email, settings)
    return True
