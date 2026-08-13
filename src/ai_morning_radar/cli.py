from __future__ import annotations

import argparse
import sys

from .pipeline import RunOptions, run
from .wecom import notify_failure


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-morning-radar", description="A股 AI 科技盘前晨报")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="生成晨报")
    run_parser.add_argument("--fixture", action="store_true", help="使用离线固定数据，不访问网络或推送")
    run_parser.add_argument("--dry-run", action="store_true", help="生成报告但不推送")
    run_parser.add_argument("--scheduled", action="store_true", help="按08:50韩国补采和09:10截止规则运行")
    run_parser.add_argument("--config", help="配置文件路径")
    failure = sub.add_parser("notify-failure", help="发送工作流失败通知")
    failure.add_argument("message", nargs="?", default="GitHub Actions 工作流失败，请检查运行日志。")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "notify-failure":
            sent = notify_failure(args.message)
            print("失败通知已发送" if sent else "未配置企业微信Webhook，无法发送失败通知")
            return 0
        report, _ = run(RunOptions(
            fixture=args.fixture, dry_run=args.dry_run, scheduled=args.scheduled, config_path=args.config
        ))
        if report:
            print(f"完成：情绪 {report.sentiment_score:+.2f}/5，模式 {report.analysis_mode}")
        return 0
    except Exception as exc:
        print(f"运行失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

