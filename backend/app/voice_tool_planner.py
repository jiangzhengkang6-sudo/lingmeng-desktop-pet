from __future__ import annotations

import re
from dataclasses import dataclass

from .controlled_tools import ToolExecuteRequest


@dataclass(frozen=True)
class VoiceToolPlan:
    """一次语音指令最多映射到一个受控工具，避免连续执行多个桌面动作。"""

    request: ToolExecuteRequest


_TIME_PATTERNS = (
    re.compile(r"(几点|几号|什么时间|当前时间|现在时间|现在的时间|日期|今天日期|今天的日期)"),
    re.compile(r"(何時|日付|現在時刻|今の時間)"),
    re.compile(r"\b(what\s+time|current\s+time|what(?:'s| is) the (?:time|date)|today'?s date|the date)\b", re.IGNORECASE),
)
_OPEN_APP_PATTERNS = (
    re.compile(r"(打开|开启|启动|起动)"),
    re.compile(r"(開く|開いて|起動)"),
    re.compile(r"\b(open|launch|start)\b", re.IGNORECASE),
)
_MUSIC_PLAY_PATTERNS = (
    re.compile(r"(想听|要听|来一?首|放(?:一?[点些首])?歌|播放|继续播放|继续放|放音乐|放歌)"),
    re.compile(r"\b(play|resume)\b", re.IGNORECASE),
)
_MUSIC_PAUSE_PATTERNS = (
    re.compile(r"(暂停|停止播放|别放(?:音乐|歌)?了|停一下音乐|先别(?:放|唱))"),
    re.compile(r"\b(pause|stop music)\b", re.IGNORECASE),
)


def plan_voice_tool(
    message: str,
    *,
    session_id: str,
    application_names: tuple[str, ...] = (),
) -> VoiceToolPlan | None:
    """将明确、低歧义的语音指令映射到白名单工具。

    这里只做本地确定性规划，不调用大模型；参数仍会交给受控工具服务做
    所有者校验、白名单校验和审计，避免语音文本绕过安全边界。
    """

    normalized = message.strip()
    if not normalized:
        return None

    if any(pattern.search(normalized) for pattern in _TIME_PATTERNS):
        return VoiceToolPlan(ToolExecuteRequest(
            tool_name="get_time",
            arguments={},
            session_id=session_id,
        ))

    lowered = normalized.casefold()
    has_music_context = bool(re.search(r"(音乐|歌|qq音乐|qq\s*音乐)", normalized, re.IGNORECASE))
    wants_pause = any(pattern.search(normalized) for pattern in _MUSIC_PAUSE_PATTERNS)
    wants_play = any(pattern.search(normalized) for pattern in _MUSIC_PLAY_PATTERNS)
    if wants_pause and has_music_context and not (wants_play and not re.search(r"(别|暂停|停止)", normalized)):
        return VoiceToolPlan(ToolExecuteRequest(
            tool_name="control_music",
            arguments={"action": "pause"},
            session_id=session_id,
        ))

    if wants_play:
        mentions_qq_music = "qq音乐".casefold() in lowered or "qq音乐" in normalized
        if has_music_context or mentions_qq_music:
            return VoiceToolPlan(ToolExecuteRequest(
                tool_name="control_music",
                arguments={"action": "play"},
                session_id=session_id,
            ))

    if any(pattern.search(normalized) for pattern in _OPEN_APP_PATTERNS):
        for app_name in sorted(application_names, key=len, reverse=True):
            candidate = app_name.strip()
            if len(candidate) >= 2 and candidate.casefold() in lowered:
                return VoiceToolPlan(ToolExecuteRequest(
                    tool_name="open_application",
                    arguments={"app_name": candidate},
                    session_id=session_id,
                ))

    return None
