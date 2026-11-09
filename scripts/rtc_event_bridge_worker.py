from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable
import json
from pathlib import Path
import sys
from typing import Any, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Settings  # noqa: E402
from backend.app.rtc_event_bridge import (  # noqa: E402
    RtcEventBridgeError,
    check_gateway,
    normalize_observation,
    submit_observation,
)
from backend.app.rtc_provider_adapter import (  # noqa: E402
    RtcProviderEventIgnored,
    create_volcengine_rtc_adapter,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将可信 RTC worker 事件转发到本地身份网关。",
    )
    parser.add_argument(
        "--provider",
        choices=("normalized", "volcengine-rtc"),
        default="normalized",
        help="输入事件格式：normalized（默认）或 volcengine-rtc 官方回调 JSONL",
    )
    parser.add_argument(
        "--task-id",
        help="本地 RTC worker 启动会话后获得的真实任务标识；官方回调模式必填",
    )
    parser.add_argument(
        "--gateway-url",
        default="http://127.0.0.1:8000",
        help="本地身份网关地址，默认 http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="标准化 JSON Lines 文件；未提供时从标准输入读取",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只执行启动检查，不提交事件",
    )
    return parser.parse_args()


def iter_event_lines(stream: TextIO) -> Iterable[tuple[int, str]]:
    for line_number, line in enumerate(stream, start=1):
        normalized = line.strip()
        if normalized:
            yield line_number, normalized


def parse_event(line: str, line_number: int) -> dict[str, Any]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RtcEventBridgeError(f"第 {line_number} 行不是有效 JSON") from exc
    if not isinstance(event, dict):
        raise RtcEventBridgeError(f"第 {line_number} 行必须是 JSON 对象")
    return event


def prepare_event_for_submission(
    event: dict[str, Any],
    *,
    provider: str,
    task_id: str | None = None,
):
    """Normalize an input event without guessing provider callback fields."""
    if provider == "normalized":
        return normalize_observation(event)
    if provider != "volcengine-rtc":
        raise RtcEventBridgeError(f"不支持的 RTC 事件提供商：{provider}")
    if event.get("type") == "voiceprint_status":
        return None
    if not task_id:
        raise RtcEventBridgeError("官方 RTC 回调模式需要 --task-id")
    return create_volcengine_rtc_adapter(task_id).adapt(event)


def safe_status_summary(line_number: int) -> str:
    """Return a diagnostic record without copying raw provider payload fields."""
    return json.dumps(
        {
            "line": line_number,
            "event": "voiceprint_status",
            "submitted": False,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def safe_unmatched_summary(line_number: int) -> str:
    """Return a diagnostic record without copying any identity or transcript data."""
    return json.dumps(
        {
            "line": line_number,
            "event": "voiceprint_unmatched",
            "submitted": False,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def run() -> int:
    args = parse_args()
    if args.provider == "volcengine-rtc" and not args.task_id and not args.check_only:
        print("官方 RTC 回调模式需要提供本地会话的 --task-id。", file=sys.stderr)
        return 2
    settings = Settings.from_environment()
    if not settings.voiceprint_rtc_configured:
        print(
            "RTC 声纹桥接配置不完整：请检查服务端 .env 中的 "
            "VOICEPRINT_PROVIDER、VOICEPRINT_RTC_OWNER_NAME、"
            "VOICEPRINT_RTC_SCORE_THRESHOLD 和 VOICEPRINT_RTC_BRIDGE_SECRET。",
            file=sys.stderr,
        )
        return 2

    try:
        status = await check_gateway(
            gateway_url=args.gateway_url,
            timeout_seconds=settings.voiceprint_rtc_timeout_seconds,
        )
    except RtcEventBridgeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.check_only:
        print(json.dumps({
            "identityBridgeConfigured": status.get("identityBridgeConfigured"),
            "openapiConfigured": status.get("openapiConfigured"),
            "message": status.get("message"),
        }, ensure_ascii=False, indent=2))
        return 0

    input_stream: TextIO
    should_close = False
    if args.input_file:
        try:
            input_stream = args.input_file.open("r", encoding="utf-8")
        except OSError as exc:
            print(f"无法打开 RTC 事件输入文件：{args.input_file}", file=sys.stderr)
            return 1
        should_close = True
    else:
        input_stream = sys.stdin

    try:
        for line_number, line in iter_event_lines(input_stream):
            try:
                event = parse_event(line, line_number)
                observation = prepare_event_for_submission(
                    event,
                    provider=args.provider,
                    task_id=args.task_id,
                )
                if observation is None:
                    print(safe_status_summary(line_number))
                    continue
                response = await submit_observation(
                    observation,
                    bridge_secret=settings.voiceprint_rtc_bridge_secret,
                    gateway_url=args.gateway_url,
                    timeout_seconds=settings.voiceprint_rtc_timeout_seconds,
                )
            except RtcProviderEventIgnored as exc:
                if exc.observation is not None:
                    try:
                        response = await submit_observation(
                            exc.observation,
                            bridge_secret=settings.voiceprint_rtc_bridge_secret,
                            gateway_url=args.gateway_url,
                            timeout_seconds=settings.voiceprint_rtc_timeout_seconds,
                        )
                    except RtcEventBridgeError as submit_error:
                        print(f"第 {line_number} 行提交失败：{submit_error}", file=sys.stderr)
                        return 1
                    print(json.dumps({
                        "accepted": False,
                        "reason": "voiceprint_unmatched",
                        "gateway": response,
                    }, ensure_ascii=False, separators=(",", ":")))
                    continue
                print(safe_unmatched_summary(line_number))
                continue
            except RtcEventBridgeError as exc:
                print(f"第 {line_number} 行提交失败：{exc}", file=sys.stderr)
                return 1
            print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    finally:
        if should_close:
            input_stream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
