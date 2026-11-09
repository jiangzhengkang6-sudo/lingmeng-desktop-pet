from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable, Mapping
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, TextIO

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import DEFAULT_VOICEPRINT_RTC_API_VERSION, Settings  # noqa: E402
from backend.app.rtc_event_bridge import (  # noqa: E402
    RTC_OBSERVATION_PATH,
    RtcEventBridgeError,
    check_gateway,
    sign_observation,
)
from backend.app.rtc_provider_adapter import (  # noqa: E402
    RtcProviderEventIgnored,
    create_volcengine_rtc_adapter,
)


MAX_CALLBACK_BYTES = 1_000_000
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8000"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查 Volcengine RTC 声纹配置、离线回调映射或真实端到端链路。",
    )
    parser.add_argument(
        "--mode",
        choices=("config", "offline", "live"),
        default="config",
        help="config=只读配置检查；offline=只解析 JSON/JSONL；live=启动真实 RTC 会话",
    )
    parser.add_argument(
        "--gateway-url",
        default=DEFAULT_GATEWAY_URL,
        help=f"本地网关地址，默认 {DEFAULT_GATEWAY_URL}",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="offline 模式的官方脱敏 JSON/JSONL 文件；未提供时从标准输入读取",
    )
    parser.add_argument(
        "--task-id",
        default="offline-task",
        help="offline 模式使用的本地占位任务号；不会提交到网关",
    )
    parser.add_argument(
        "--expect-match",
        action="store_true",
        help="offline 模式要求至少找到一个 voiceprintName/voiceprintScore 匹配",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="live 模式的显式安全确认；没有此参数不会调用 StartVoiceChat",
    )
    parser.add_argument(
        "--callback-file",
        type=Path,
        help="已废弃：live 模式现在直接接收官方 RTS HTTP 回调，不再使用手工 JSONL 文件",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=120.0,
        help="live 模式等待真实回调的秒数，默认 120",
    )
    parser.add_argument(
        "--room-id",
        default="desktop-pet-identity",
        help="live 模式 RTC 房间号",
    )
    parser.add_argument(
        "--agent-user-id",
        default="desktop-pet-agent",
        help="live 模式智能体用户号",
    )
    parser.add_argument(
        "--target-user-id",
        action="append",
        dest="target_user_ids",
        help="live 模式目标用户号，可重复指定；默认 desktop-owner",
    )
    parser.add_argument(
        "--reset-identity-after",
        action="store_true",
        help="live 模式结束后调用本地 reset 接口，把身份状态恢复为 unknown",
    )
    return parser.parse_args()


def emit(payload: Mapping[str, Any]) -> None:
    output = json.dumps(dict(payload), ensure_ascii=False, indent=2)
    stdout = sys.stdout
    reconfigure = getattr(stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")
    stdout.write(output)
    stdout.write("\n")


def safe_scene_summary(settings: Settings) -> dict[str, Any]:
    path = settings.voiceprint_rtc_scene_path
    summary: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "validJson": False,
        "voiceprintConfigured": False,
        "voiceprintCount": 0,
        "streamMode": None,
    }
    if not path.is_file():
        return summary
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return summary
    if not isinstance(payload, dict):
        return summary
    summary["validJson"] = True
    agent_config = payload.get("AgentConfig")
    voiceprint = agent_config.get("VoicePrint") if isinstance(agent_config, dict) else None
    if isinstance(voiceprint, dict):
        ids = voiceprint.get("IdList")
        summary["voiceprintCount"] = len(ids) if isinstance(ids, list) else 0
        summary["voiceprintConfigured"] = (
            voiceprint.get("Mode") == 2
            and summary["voiceprintCount"] > 0
            and isinstance(voiceprint.get("Score"), (int, float))
        )
    config = payload.get("Config")
    asr_config = config.get("ASRConfig") if isinstance(config, dict) else None
    provider_params = (
        asr_config.get("ProviderParams")
        if isinstance(asr_config, dict)
        else None
    )
    if isinstance(provider_params, dict):
        summary["streamMode"] = provider_params.get("StreamMode")
    return summary


async def run_config_check(args: argparse.Namespace) -> int:
    settings = Settings.from_environment()
    scene = safe_scene_summary(settings)
    result: dict[str, Any] = {
        "mode": "config",
        "provider": settings.voiceprint_provider,
        "identityBridgeConfigured": settings.voiceprint_rtc_configured,
        "openapiConfigured": settings.voiceprint_rtc_openapi_configured,
        "ownerNameConfigured": bool(settings.voiceprint_rtc_owner_name),
        "scoreThreshold": settings.voiceprint_rtc_score_threshold,
        "bridgeSecretConfigured": bool(settings.voiceprint_rtc_bridge_secret),
        "callbackUrlConfigured": bool(settings.voiceprint_rtc_callback_url),
        "callbackSecretConfigured": bool(settings.voiceprint_rtc_callback_secret),
        "callbackConfigured": settings.voiceprint_rtc_callback_configured,
        "liveConfigured": settings.voiceprint_rtc_live_configured,
        "accessKeyConfigured": bool(settings.voiceprint_rtc_access_key_id),
        "secretAccessKeyConfigured": bool(settings.voiceprint_rtc_secret_access_key),
        "appIdConfigured": bool(settings.voiceprint_rtc_app_id),
        "apiVersion": settings.voiceprint_rtc_api_version,
        "usesCurrentApiVersion": (
            settings.voiceprint_rtc_api_version == DEFAULT_VOICEPRINT_RTC_API_VERSION
        ),
        "scene": scene,
    }
    try:
        status = await check_gateway(
            gateway_url=args.gateway_url,
            timeout_seconds=settings.voiceprint_rtc_timeout_seconds,
        )
        result["gateway"] = {
            "reachable": True,
            "identityBridgeConfigured": status.get("identityBridgeConfigured"),
            "openapiConfigured": status.get("openapiConfigured"),
            "sceneConfigured": status.get("sceneConfigured"),
            "sessionControlAvailable": status.get("sessionControlAvailable"),
            "callbackConfigured": status.get("callbackConfigured"),
            "liveConfigured": status.get("liveConfigured"),
            "apiVersion": status.get("apiVersion"),
        }
    except RtcEventBridgeError as exc:
        result["gateway"] = {"reachable": False, "error": str(exc)}

    emit(result)
    required = (
        settings.voiceprint_rtc_configured
        and settings.voiceprint_rtc_openapi_configured
        and scene["exists"]
        and scene["validJson"]
        and scene["voiceprintConfigured"]
        and result["gateway"].get("reachable") is True
        and result["gateway"].get("identityBridgeConfigured") is True
        and settings.voiceprint_rtc_callback_configured
        and result["gateway"].get("callbackConfigured") is True
        and result["gateway"].get("liveConfigured") is True
    )
    return 0 if required else 1


def read_input_text(stream: TextIO) -> str:
    content = stream.read(MAX_CALLBACK_BYTES + 1)
    if len(content.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise RtcEventBridgeError("RTC 回调输入超过 1 MB")
    if not content.strip():
        raise RtcEventBridgeError("RTC 回调输入为空")
    return content


def load_json_or_jsonl(raw: str) -> list[tuple[int, dict[str, Any]]]:
    """Load one JSON object, a JSON array, or JSON Lines without printing values."""
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        events: list[tuple[int, dict[str, Any]]] = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            normalized = line.strip()
            if not normalized:
                continue
            try:
                event = json.loads(normalized)
            except json.JSONDecodeError as exc:
                raise RtcEventBridgeError(f"第 {line_number} 行不是有效 JSON") from exc
            if not isinstance(event, dict):
                raise RtcEventBridgeError(f"第 {line_number} 行必须是 JSON 对象")
            events.append((line_number, event))
        if not events:
            raise RtcEventBridgeError("输入不是有效 JSON 或 JSONL")
        return events

    if isinstance(document, dict):
        return [(1, document)]
    if isinstance(document, list):
        events = []
        for index, event in enumerate(document, start=1):
            if not isinstance(event, dict):
                raise RtcEventBridgeError(f"JSON 数组第 {index} 项必须是对象")
            events.append((index, event))
        if not events:
            raise RtcEventBridgeError("JSON 数组为空")
        return events
    raise RtcEventBridgeError("输入必须是 JSON 对象、JSON 数组或 JSONL")


def load_callback_file(path: Path) -> list[tuple[int, dict[str, Any]]]:
    try:
        return load_json_or_jsonl(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RtcEventBridgeError(f"无法读取 RTC 回调文件：{path}") from exc


def run_offline_check(args: argparse.Namespace) -> int:
    input_stream: TextIO = sys.stdin
    should_close = False
    if args.input_file:
        try:
            input_stream = args.input_file.open("r", encoding="utf-8")
        except OSError as exc:
            print(f"无法打开 RTC 回调文件：{args.input_file}", file=sys.stderr)
            return 1
        should_close = True

    try:
        try:
            events = load_json_or_jsonl(read_input_text(input_stream))
            adapter = create_volcengine_rtc_adapter(args.task_id)
        except RtcEventBridgeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        mapped_count = 0
        ignored_count = 0
        error_count = 0
        results: list[dict[str, Any]] = []
        for line_number, event in events:
            if event.get("type") == "voiceprint_status":
                ignored_count += 1
                results.append({
                    "line": line_number,
                    "event": "voiceprint_status",
                    "mapped": False,
                    "submitted": False,
                })
                continue
            try:
                observation = adapter.adapt(event)
            except RtcProviderEventIgnored:
                ignored_count += 1
                results.append({
                    "line": line_number,
                    "event": "voiceprint_unmatched",
                    "mapped": False,
                    "submitted": False,
                })
                continue
            except RtcEventBridgeError as exc:
                error_count += 1
                results.append({
                    "line": line_number,
                    "event": "invalid_or_unsupported",
                    "mapped": False,
                    "submitted": False,
                    "error": str(exc),
                })
                continue
            mapped_count += 1
            results.append({
                "line": line_number,
                "event": "subtitle",
                "mapped": True,
                "submitted": False,
                "voiceprintName": observation.voiceprint_name,
                "voiceprintScore": observation.voiceprint_score,
            })

        emit({
            "mode": "offline",
            "submitted": False,
            "events": results,
            "mappedCount": mapped_count,
            "ignoredCount": ignored_count,
            "errorCount": error_count,
        })
        if error_count:
            return 1
        if args.expect_match and mapped_count == 0:
            return 1
        return 0
    finally:
        if should_close:
            input_stream.close()


async def post_signed_observation(
    observation: Mapping[str, Any],
    *,
    settings: Settings,
    gateway_url: str,
) -> tuple[int, dict[str, Any]]:
    """Submit one observation directly only for the post-stop rejection assertion."""
    signed = sign_observation(observation, settings.voiceprint_rtc_bridge_secret)
    async with httpx.AsyncClient(timeout=settings.voiceprint_rtc_timeout_seconds) as client:
        response = await client.post(
            gateway_url.rstrip("/") + RTC_OBSERVATION_PATH,
            content=signed.body,
            headers=signed.headers,
        )
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return response.status_code, payload if isinstance(payload, dict) else {}


async def wait_for_callback(path: Path, timeout_seconds: float) -> None:
    if timeout_seconds <= 0:
        raise RtcEventBridgeError("等待回调时间必须大于 0")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            return
        await asyncio.sleep(0.25)
    raise RtcEventBridgeError(
        f"在 {timeout_seconds:g} 秒内没有等到官方 RTC SDK 写入回调文件：{path}"
    )


def run_worker(
    *,
    task_id: str,
    callback_file: Path,
    gateway_url: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "rtc_event_bridge_worker.py"),
            "--provider",
            "volcengine-rtc",
            "--task-id",
            task_id,
            "--gateway-url",
            gateway_url,
            "--input-file",
            str(callback_file),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def worker_has_owner_verified(stdout: str) -> bool:
    for line in stdout.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("status") == "owner_verified":
            return True
    return False


def first_mapped_observation(
    events: Iterable[tuple[int, dict[str, Any]]],
    task_id: str,
) -> dict[str, Any] | None:
    adapter = create_volcengine_rtc_adapter(task_id)
    for _, event in events:
        try:
            observation = adapter.adapt(event)
        except (RtcProviderEventIgnored, RtcEventBridgeError):
            continue
        return observation.model_dump(mode="json")
    return None


async def start_live_session(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], Settings]:
    settings = Settings.from_environment()
    target_user_ids = args.target_user_ids or [settings.voiceprint_rtc_owner_name or "desktop-owner"]
    payload = {
        "roomId": args.room_id,
        "agentUserId": args.agent_user_id,
        "targetUserIds": target_user_ids,
        "purpose": "identity_verification",
        "confirmed": True,
    }
    async with httpx.AsyncClient(timeout=settings.voiceprint_rtc_timeout_seconds) as client:
        response = await client.post(
            args.gateway_url.rstrip("/") + "/api/identity/rtc/sessions",
            json=payload,
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise RtcEventBridgeError("RTC 会话启动接口返回了无效 JSON") from exc
    if response.status_code >= 400:
        raise RtcEventBridgeError(f"RTC 会话启动失败（HTTP {response.status_code}）")
    if not isinstance(body, dict):
        raise RtcEventBridgeError("RTC 会话启动接口返回格式无效")
    task_id = body.get("taskId") or body.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise RtcEventBridgeError("RTC 会话启动响应中没有 TaskId")
    return {
        "taskId": task_id,
        "roomId": body.get("roomId") or args.room_id,
        "appId": body.get("appId"),
    }, settings


async def stop_live_session(
    task_id: str,
    *,
    args: argparse.Namespace,
    settings: Settings,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=settings.voiceprint_rtc_timeout_seconds) as client:
        response = await client.delete(
            args.gateway_url.rstrip("/") + f"/api/identity/rtc/sessions/{task_id}",
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise RtcEventBridgeError("RTC 会话停止接口返回了无效 JSON") from exc
    if response.status_code >= 400:
        raise RtcEventBridgeError(f"RTC 会话停止失败（HTTP {response.status_code}）")
    return body if isinstance(body, dict) else {}


async def reset_identity(args: argparse.Namespace, settings: Settings) -> None:
    async with httpx.AsyncClient(timeout=settings.voiceprint_rtc_timeout_seconds) as client:
        response = await client.post(args.gateway_url.rstrip("/") + "/api/identity/reset")
    if response.status_code >= 400:
        raise RtcEventBridgeError(f"身份状态清理失败（HTTP {response.status_code}）")


async def get_identity_snapshot(
    args: argparse.Namespace,
    settings: Settings,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=settings.voiceprint_rtc_timeout_seconds) as client:
        response = await client.get(args.gateway_url.rstrip("/") + "/api/identity")
    if response.status_code >= 400:
        raise RtcEventBridgeError(f"身份状态查询失败（HTTP {response.status_code}）")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RtcEventBridgeError("身份状态接口返回格式无效")
    return payload


async def wait_for_live_identity(
    args: argparse.Namespace,
    settings: Settings,
) -> dict[str, Any]:
    if args.wait_seconds <= 0:
        raise RtcEventBridgeError("等待真实 RTS 回调的时间必须大于 0")
    deadline = time.monotonic() + args.wait_seconds
    last_status = "unknown"
    while time.monotonic() < deadline:
        snapshot = await get_identity_snapshot(args, settings)
        status = snapshot.get("status")
        last_status = status if isinstance(status, str) else last_status
        if status == "owner_verified":
            return snapshot
        if status == "guest":
            raise RtcEventBridgeError(
                "官方 RTS 回调已到达，但当前说话人未通过主人声纹校验（guest）"
            )
        await asyncio.sleep(1.0)
    raise RtcEventBridgeError(
        f"在 {args.wait_seconds:g} 秒内没有等到可判定身份的官方 RTS 回调；最后状态：{last_status}"
    )


async def run_live_check(args: argparse.Namespace) -> int:
    if not args.live:
        print(
            "live 模式不会默认触发真实云端调用；请显式追加 --live，并先配置官方 RTS HTTPS 回调地址。",
            file=sys.stderr,
        )
        return 2

    settings = Settings.from_environment()
    session: dict[str, Any] | None = None
    task_id: str | None = None
    result: dict[str, Any] = {
        "mode": "live",
        "transport": "official-rts-http-callback",
        "callbackFileUsed": False,
        "rtsCallbackReceived": False,
    }
    try:
        if not settings.voiceprint_rtc_live_configured:
            raise RtcEventBridgeError(
                "RTC live 验收尚未就绪：需要配置 VOICEPRINT_RTC_CALLBACK_URL 和 "
                "VOICEPRINT_RTC_CALLBACK_SECRET，且回调地址必须为公网 HTTPS"
            )
        gateway_status = await check_gateway(
            gateway_url=args.gateway_url,
            timeout_seconds=settings.voiceprint_rtc_timeout_seconds,
        )
        if gateway_status.get("callbackConfigured") is not True:
            raise RtcEventBridgeError("本地网关尚未启用官方 RTS 回调配置")
        if gateway_status.get("liveConfigured") is not True:
            raise RtcEventBridgeError("本地网关 live 验收条件未全部就绪")

        session, settings = await start_live_session(args)
        task_id = str(session["taskId"])
        result["started"] = {
            "taskId": task_id,
            "roomId": session.get("roomId"),
            "appIdReturned": bool(session.get("appId")),
        }
        print(f"RTC 会话已启动，AppId={session.get('appId')}，TaskId={task_id}")
        print("请使用相同 AppId、RoomId 和 desktop-owner 的 RTC Token 让官方客户端/SDK 入房并持续自然说话。")

        identity = await wait_for_live_identity(args, settings)
        result["rtsCallbackReceived"] = True
        result["identity"] = {
            "status": identity.get("status"),
            "adapter": identity.get("adapter"),
            "canReadPrivateMemory": identity.get("can_read_private_memory"),
            "canUseTools": identity.get("can_use_tools"),
        }

        await stop_live_session(task_id, args=args, settings=settings)
        result["stopped"] = True

        replay_observation = {
            "task_id": task_id,
            "voiceprint_name": settings.voiceprint_rtc_owner_name,
            "voiceprint_score": settings.voiceprint_rtc_score_threshold,
        }
        status_code, payload = await post_signed_observation(
            replay_observation,
            settings=settings,
            gateway_url=args.gateway_url,
        )
        detail = payload.get("detail") if isinstance(payload, dict) else None
        stop_rejection_code = detail.get("code") if isinstance(detail, dict) else None
        result["stoppedCallbackRejection"] = {
            "httpStatus": status_code,
            "code": stop_rejection_code,
            "passed": status_code == 409 and stop_rejection_code == "RTC_SESSION_NOT_ACTIVE",
        }
        if not result["stoppedCallbackRejection"]["passed"]:
            raise RtcEventBridgeError(
                "停止会话后的旧回调未按预期返回 RTC_SESSION_NOT_ACTIVE"
            )
        result["passed"] = True
        emit(result)
        return 0
    except (RtcEventBridgeError, httpx.HTTPError) as exc:
        result["passed"] = False
        result["error"] = str(exc)
        emit(result)
        return 1
    finally:
        if task_id is not None and not result.get("stopped"):
            try:
                await stop_live_session(task_id, args=args, settings=settings)
            except Exception:
                pass
        if args.reset_identity_after:
            try:
                await reset_identity(args, settings)
            except Exception:
                pass


async def main() -> int:
    args = parse_args()
    if args.mode == "config":
        return await run_config_check(args)
    if args.mode == "offline":
        return run_offline_check(args)
    return await run_live_check(args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
