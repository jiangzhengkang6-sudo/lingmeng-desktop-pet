from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Settings  # noqa: E402
from backend.app.rtc_event_bridge import (  # noqa: E402
    RtcEventBridgeError,
    submit_observation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="提交一个由可信 RTC worker 标准化得到的声纹识别事件。",
    )
    parser.add_argument("--task-id", required=True, help="RTC VoiceChat 任务 ID")
    parser.add_argument("--voiceprint-name", required=True, help="RTC 返回的已注册声纹名称")
    parser.add_argument("--score", required=True, type=float, help="RTC 返回的声纹分数，范围 1-100")
    parser.add_argument(
        "--gateway-url",
        default="http://127.0.0.1:8000",
        help="本地身份网关地址，默认 http://127.0.0.1:8000",
    )
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
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
        response = await submit_observation(
            {
                "task_id": args.task_id,
                "voiceprint_name": args.voiceprint_name,
                "voiceprint_score": args.score,
            },
            bridge_secret=settings.voiceprint_rtc_bridge_secret,
            gateway_url=args.gateway_url,
            timeout_seconds=settings.voiceprint_rtc_timeout_seconds,
        )
    except RtcEventBridgeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
