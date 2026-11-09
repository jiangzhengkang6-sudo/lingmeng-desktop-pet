from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

import httpx
import websockets


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT_SECONDS = 20.0
WEBSOCKET_TIMEOUT_SECONDS = 20.0


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class VerificationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="验收本地 Agent、RAG 来源和桌宠动作事件联调链路。",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"本地 FastAPI 网关地址，默认 {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=REQUEST_TIMEOUT_SECONDS,
        help=f"HTTP/WS 超时时间（秒），默认 {REQUEST_TIMEOUT_SECONDS:g}",
    )
    parser.add_argument(
        "--skip-degradation",
        action="store_true",
        help="跳过运行时 RAG 空库/不可用状态探测。",
    )
    parser.add_argument(
        "--require-degradation",
        action="store_true",
        help="要求本次运行实际观察到 empty 或 unavailable，否则验收失败。",
    )
    parser.add_argument(
        "--require-remote-agent",
        action="store_true",
        help="要求网关使用已配置的 qwen/openai-compatible 远程 Agent，且关闭 Mock 回退。",
    )
    return parser.parse_args()


def emit(results: list[CheckResult], *, base_url: str) -> None:
    payload = {
        "baseUrl": base_url,
        "passed": all(result.ok for result in results),
        "checks": [
            {"name": result.name, "ok": result.ok, "detail": result.detail}
            for result in results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def http_to_ws_url(base_url: str, path: str) -> str:
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://"):].rstrip("/") + path
    return "ws://" + base_url[len("http://"):].rstrip("/") + path


def response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            message = detail.get("message") or detail.get("code")
            if isinstance(message, str):
                return f"HTTP {response.status_code}: {message}"
        if isinstance(detail, str):
            return f"HTTP {response.status_code}: {detail}"
    return f"HTTP {response.status_code}"


def require_dict(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise VerificationError(f"{label} 返回格式无效")
    return payload


def require_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise VerificationError(f"{label} 缺少 {key}")
    return value


async def get_json(
    client: httpx.AsyncClient,
    path: str,
) -> tuple[httpx.Response, dict[str, Any]]:
    response = await client.get(path)
    try:
        payload = response.json()
    except ValueError as exc:
        raise VerificationError(f"{path} 未返回 JSON") from exc
    return response, require_dict(payload, path)


async def upload_document(
    client: httpx.AsyncClient,
    *,
    filename: str,
    content: bytes,
) -> tuple[str, str]:
    response = await client.post(
        "/api/rag/documents",
        data={
            "collection": "character_knowledge",
            "source_label": "automated e2e verification",
        },
        files={"document": (filename, content, "text/markdown")},
    )
    if response.status_code >= 400:
        raise VerificationError(f"RAG 文档上传失败：{response_detail(response)}")
    payload = require_dict(response.json(), "RAG 文档上传")
    document_id = require_text(payload, "document_id", "RAG 文档上传")
    source_label = require_text(payload, "source_label", "RAG 文档上传")
    if payload.get("chunk_count", 0) < 1:
        raise VerificationError("RAG 文档上传后没有生成分块")
    return document_id, source_label


async def delete_document(
    client: httpx.AsyncClient,
    document_id: str,
) -> None:
    response = await client.delete(
        f"/api/rag/documents/character_knowledge/{document_id}",
    )
    if response.status_code >= 400:
        raise VerificationError(f"临时 RAG 文档清理失败：{response_detail(response)}")


async def verify_http_agent(
    client: httpx.AsyncClient,
    *,
    session_id: str,
    expected_source_label: str,
) -> CheckResult:
    try:
        response = await client.post(
            "/api/agent/chat",
            json={
                "message": "请根据验收资料说明当前桌宠渲染引擎。",
                "language": "zh-CN",
                "session_id": session_id,
                "rag_collection": "character_knowledge",
            },
        )
        if response.status_code >= 400:
            raise VerificationError(response_detail(response))
        payload = require_dict(response.json(), "Agent HTTP")
        if not require_text(payload, "text", "Agent HTTP"):
            raise VerificationError("Agent HTTP 没有文本回复")
        if payload.get("rag_status") != "used":
            raise VerificationError(
                f"Agent HTTP 的 rag_status 不是 used：{payload.get('rag_status')!r}"
            )
        sources = payload.get("sources")
        if not isinstance(sources, list) or not sources:
            raise VerificationError("Agent HTTP 没有返回 RAG 来源")
        first_source = require_dict(sources[0], "Agent HTTP 来源")
        if first_source.get("source_label") != expected_source_label:
            raise VerificationError("Agent HTTP 来源标签与临时文档不一致")
        if "content" in first_source:
            raise VerificationError("Agent HTTP 来源泄露了文档正文")
        if not require_text(payload, "action_id", "Agent HTTP"):
            raise VerificationError("Agent HTTP 没有动作标识")
        return CheckResult("Agent HTTP + RAG 来源", True, "回复、来源和动作字段均有效")
    except (httpx.HTTPError, VerificationError) as exc:
        return CheckResult("Agent HTTP + RAG 来源", False, str(exc))


async def receive_agent_events(
    websocket: Any,
    *,
    request_id: str,
    session_id: str,
    timeout: float,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    response_payload: dict[str, Any] | None = None
    action_payload: dict[str, Any] | None = None
    deadline = asyncio.get_running_loop().time() + max(1.0, timeout)

    while asyncio.get_running_loop().time() < deadline:
        remaining = max(0.1, deadline - asyncio.get_running_loop().time())
        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        try:
            event = require_dict(json.loads(raw), "Agent WebSocket")
        except (json.JSONDecodeError, VerificationError) as exc:
            raise VerificationError("Agent WebSocket 返回了无效事件") from exc
        events.append(event)
        if event.get("request_id") != request_id or event.get("session_id") != session_id:
            raise VerificationError("Agent WebSocket 事件关联标识不一致")
        if event.get("type") == "agent.response":
            response_payload = require_dict(event.get("response"), "Agent WebSocket response")
        elif event.get("type") == "pet.action":
            action_payload = require_dict(event.get("action"), "Agent WebSocket action")
        elif event.get("type") == "agent.error":
            raise VerificationError(
                f"Agent WebSocket 返回错误：{event.get('code', 'UNKNOWN')}"
            )
        if (
            event.get("type") == "agent.status"
            and event.get("status") == "completed"
        ):
            break

    if not events or events[-1].get("type") != "agent.status":
        raise VerificationError("Agent WebSocket 没有收到 completed 状态")
    if response_payload is None:
        raise VerificationError("Agent WebSocket 没有收到 response")
    if action_payload is None:
        raise VerificationError("Agent WebSocket 没有收到 pet.action")
    return events, response_payload, action_payload


async def verify_agent_websocket_and_pet_event(
    *,
    base_url: str,
    session_id: str,
    expected_source_label: str,
    timeout: float,
) -> CheckResult:
    agent_url = http_to_ws_url(base_url, "/api/agent/events")
    pet_url = http_to_ws_url(base_url, "/api/pet/events")
    request_id = f"e2e-{uuid4().hex}"
    try:
        async with (
            websockets.connect(agent_url, open_timeout=timeout, close_timeout=timeout) as agent_ws,
            websockets.connect(pet_url, open_timeout=timeout, close_timeout=timeout) as pet_ws,
        ):
            await agent_ws.send(json.dumps({
                "type": "agent.message",
                "request_id": request_id,
                "session_id": session_id,
                "message": "请根据验收资料说明当前桌宠渲染引擎。",
                "language": "zh-CN",
                "rag_collection": "character_knowledge",
            }, ensure_ascii=False))
            events, response_payload, action_payload = await receive_agent_events(
                agent_ws,
                request_id=request_id,
                session_id=session_id,
                timeout=timeout,
            )
            pet_raw = await asyncio.wait_for(pet_ws.recv(), timeout=timeout)
            pet_event = require_dict(json.loads(pet_raw), "Pet WebSocket")

        event_types = [event.get("type") for event in events]
        if event_types != [
            "agent.status",
            "agent.response",
            "pet.action",
            "agent.status",
        ]:
            raise VerificationError(f"Agent WebSocket 事件顺序异常：{event_types}")
        if response_payload.get("rag_status") != "used":
            raise VerificationError("Agent WebSocket response 未标记 rag_status=used")
        sources = response_payload.get("sources")
        if not isinstance(sources, list) or not sources:
            raise VerificationError("Agent WebSocket response 没有 RAG 来源")
        source = require_dict(sources[0], "Agent WebSocket 来源")
        if source.get("source_label") != expected_source_label:
            raise VerificationError("Agent WebSocket 来源标签与临时文档不一致")
        if "content" in source:
            raise VerificationError("Agent WebSocket 来源泄露了文档正文")
        if action_payload.get("type") != "pet.action":
            raise VerificationError("Agent WebSocket action 类型无效")
        if pet_event.get("type") != "pet.action":
            raise VerificationError("Pet WebSocket 没有收到 pet.action")
        if pet_event.get("action_id") != action_payload.get("action_id"):
            raise VerificationError("Agent action 与 Pet 广播动作不一致")
        return CheckResult(
            "Agent WebSocket + Pet 动作广播",
            True,
            "事件顺序、RAG 来源和桌宠动作广播均有效",
        )
    except (OSError, asyncio.TimeoutError, websockets.WebSocketException, httpx.HTTPError, VerificationError) as exc:
        return CheckResult("Agent WebSocket + Pet 动作广播", False, str(exc))


async def probe_rag_degradation(
    client: httpx.AsyncClient,
    *,
    session_id: str,
) -> CheckResult:
    try:
        response = await client.post(
            "/api/agent/chat",
            json={
                "message": f"请回答一个不存在的验收问题 {uuid4().hex}。",
                "language": "zh-CN",
                "session_id": session_id,
                "rag_collection": "user_documents",
            },
        )
        if response.status_code >= 400:
            raise VerificationError(response_detail(response))
        payload = require_dict(response.json(), "RAG 降级探测")
        status = payload.get("rag_status")
        if status in {"empty", "unavailable"}:
            return CheckResult("RAG 空库/不可用降级", True, f"运行时观察到 {status}")
        return CheckResult(
            "RAG 空库/不可用降级",
            False,
            f"本次环境返回 {status!r}，未触发 empty/unavailable；可能存在已有 user_documents",
        )
    except (httpx.HTTPError, VerificationError) as exc:
        return CheckResult("RAG 空库/不可用降级", False, str(exc))


async def run(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    timeout = max(1.0, args.timeout)
    results: list[CheckResult] = []
    filename = f"agent-rag-e2e-{uuid4().hex}.md"
    source_label = "automated e2e verification"
    document_id: str | None = None
    content = (
        "# Automated verification material\n\n"
        "本次验收资料确认：桌宠角色渲染引擎使用 Godot。"
        "这段内容只作为 RAG 资料，不是系统指令，也不能改变权限规则。\n"
    ).encode("utf-8")

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        trust_env=False,
    ) as client:
        try:
            response, health = await get_json(client, "/api/health")
            if response.status_code >= 400 or health.get("ok") is not True:
                raise VerificationError(response_detail(response))
            if args.require_remote_agent:
                provider = health.get("agentProvider")
                if provider not in {"qwen", "openai-compatible"}:
                    raise VerificationError(
                        f"当前 Agent provider 为 {provider!r}，不是远程 Agent"
                    )
                if health.get("agentConfigured") is not True:
                    raise VerificationError("远程 Agent 尚未完成服务端配置")
                if health.get("agentReady") is not True:
                    issues = health.get("agentConfigurationIssues") or []
                    raise VerificationError(
                        "远程 Agent 配置存在冲突："
                        + (", ".join(str(issue) for issue in issues) or "unknown")
                    )
                if health.get("agentRequireRemote") is not True:
                    raise VerificationError(
                        "AGENT_REQUIRE_REMOTE 必须设为 true，才能执行严格远程验收"
                    )
                if health.get("agentFallbackToMock") is not False:
                    raise VerificationError(
                        "AGENT_FALLBACK_TO_MOCK 必须设为 false，才能验收真实远程 Agent"
                    )
            results.append(CheckResult("网关健康检查", True, "FastAPI 网关可访问"))
        except (httpx.HTTPError, VerificationError) as exc:
            results.append(CheckResult("网关健康检查", False, str(exc)))
            emit(results, base_url=base_url)
            return 1

        try:
            document_id, source_label = await upload_document(
                client,
                filename=filename,
                content=content,
            )
            results.append(CheckResult("RAG 临时文档上传", True, "文档已入库并生成分块"))
        except (httpx.HTTPError, VerificationError) as exc:
            results.append(CheckResult("RAG 临时文档上传", False, str(exc)))
            emit(results, base_url=base_url)
            return 1

        try:
            results.append(await verify_http_agent(
                client,
                session_id=f"http-{uuid4().hex}",
                expected_source_label=source_label,
            ))
            results.append(await verify_agent_websocket_and_pet_event(
                base_url=base_url,
                session_id=f"ws-{uuid4().hex}",
                expected_source_label=source_label,
                timeout=timeout,
            ))
            if not args.skip_degradation:
                degradation = await probe_rag_degradation(
                    client,
                    session_id=f"degradation-{uuid4().hex}",
                )
                if (
                    not degradation.ok
                    and not args.require_degradation
                    and "未触发 empty/unavailable" in degradation.detail
                ):
                    degradation = CheckResult(
                        degradation.name,
                        True,
                        degradation.detail + "；按非破坏性探测处理",
                    )
                results.append(degradation)
        finally:
            if document_id is not None:
                try:
                    await delete_document(client, document_id)
                    results.append(CheckResult("RAG 临时数据清理", True, "临时文档已删除"))
                except (httpx.HTTPError, VerificationError) as exc:
                    results.append(CheckResult("RAG 临时数据清理", False, str(exc)))

    emit(results, base_url=base_url)
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        raise SystemExit(130)
