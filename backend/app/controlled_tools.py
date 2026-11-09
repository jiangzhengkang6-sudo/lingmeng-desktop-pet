from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Iterator, Literal, Mapping
from uuid import uuid4

import ctypes
from ctypes import wintypes

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .identity import IdentitySnapshot


RiskLevel = Literal["low", "medium", "high"]
ApprovalState = Literal["auto_approved", "pending", "approved", "rejected"]
ExecutionState = Literal["pending", "success", "failure", "rejected"]
MusicAction = Literal["play", "pause"]

MAX_SEARCH_RESULTS = 100
APPROVAL_TTL_SECONDS = 10 * 60
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_SPACE = 0x20
KEYEVENTF_KEYUP = 0x0002


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    description: str
    risk_level: RiskLevel
    requires_owner: bool
    requires_confirmation: bool
    enabled: bool = True
    unavailable_reason: str | None = None


class ToolExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str = Field(default="tool-session", min_length=1, max_length=128)
    # 可选幂等键：相同会话内重复提交时，工作流会复用稳定的工具调用标识。
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("tool_name", "session_id")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("内容不能为空")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def normalize_idempotency_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ToolCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    risk_level: RiskLevel
    status: ExecutionState
    approval: ApprovalState
    requires_confirmation: bool
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    audit_id: str
    created_at: str


class ToolApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    call_id: str
    session_id: str
    tool_name: str
    risk_level: RiskLevel
    arguments: dict[str, Any]
    status: Literal["pending", "approved", "rejected", "expired"]
    created_at: str
    updated_at: str
    expires_at: str


class ToolAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str
    call_id: str
    session_id: str
    speaker_identity: str
    tool_name: str
    risk_level: RiskLevel
    approval: ApprovalState
    status: ExecutionState
    arguments_summary: str
    result_summary: str | None = None
    error_code: str | None = None
    created_at: str


class ToolPolicyError(Exception):
    def __init__(self, message: str, code: str = "TOOL_POLICY_DENIED", status_code: int = 403):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ToolValidationError(ToolPolicyError):
    def __init__(self, message: str, code: str = "INVALID_TOOL_ARGUMENTS"):
        super().__init__(message, code, 422)


class ControlledToolService:
    """Allowlisted desktop capabilities with explicit approval and audit records."""

    def __init__(
        self,
        database_path: Path,
        allowed_directories: tuple[Path, ...] = (),
        allowed_applications: Mapping[str, str] | None = None,
    ):
        self.database_path = Path(database_path)
        self.allowed_directories = tuple(path.expanduser().resolve() for path in allowed_directories)
        self.allowed_applications = {
            name.strip(): command.strip()
            for name, command in (allowed_applications or {}).items()
            if name.strip() and command.strip()
        }
        self._lock = Lock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_time",
                label="查询时间",
                description="查询本机当前日期、时间和时区。",
                risk_level="low",
                requires_owner=False,
                requires_confirmation=False,
            ),
            ToolDefinition(
                name="search_files",
                label="查找文件",
                description="只在已授权目录内按文件名查找文件。",
                risk_level="low",
                requires_owner=True,
                requires_confirmation=False,
                enabled=bool(self.allowed_directories),
                unavailable_reason=None if self.allowed_directories else "尚未配置授权目录",
            ),
            ToolDefinition(
                name="open_application",
                label="打开白名单应用",
                description="只启动已登记的应用名称，不接受任意命令或参数。",
                risk_level="low",
                requires_owner=True,
                requires_confirmation=False,
                enabled=bool(self.allowed_applications),
                unavailable_reason=None if self.allowed_applications else "尚未配置白名单应用",
            ),
            ToolDefinition(
                name="open_file",
                label="打开指定文件",
                description="打开授权目录内的指定文件，需要界面审批。",
                risk_level="medium",
                requires_owner=True,
                requires_confirmation=True,
                enabled=bool(self.allowed_directories),
                unavailable_reason=None if self.allowed_directories else "尚未配置授权目录",
            ),
            ToolDefinition(
                name="control_music",
                label="控制音乐播放",
                description="控制 QQ 音乐播放或暂停，不读取账号数据。",
                risk_level="low",
                requires_owner=True,
                requires_confirmation=False,
                enabled="QQ音乐" in self.allowed_applications,
                unavailable_reason=None if "QQ音乐" in self.allowed_applications else "尚未配置 QQ 音乐",
            ),
        ]

    def enabled_application_names(self) -> tuple[str, ...]:
        """返回可被语音 Agent 选择的白名单应用名称。"""

        return tuple(sorted(self.allowed_applications))

    def list_approvals(self, status: str | None = "pending", limit: int = 50) -> list[ToolApproval]:
        query = """
            SELECT approval_id, call_id, session_id, tool_name, risk_level, arguments_json, status,
                   created_at, updated_at, expires_at
            FROM tool_approvals
        """
        parameters: list[Any] = []
        if status:
            query += " WHERE status = ?"
            parameters.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(max(1, min(limit, 100)))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._approval_from_row(row) for row in rows]

    def get_approval(self, approval_id: str) -> ToolApproval:
        """按审批标识读取审批单，供工作流恢复前定位调用标识。"""

        with self._locked_connection() as connection:
            row = connection.execute(
                """
                SELECT approval_id, call_id, session_id, tool_name, risk_level, arguments_json, status,
                       created_at, updated_at, expires_at
                FROM tool_approvals WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
        if row is None:
            raise ToolPolicyError("审批请求不存在", "APPROVAL_NOT_FOUND", 404)
        return self._approval_from_row(row)

    def get_approval_by_call_id(self, call_id: str) -> ToolApproval:
        """按稳定调用标识读取审批单，供中断恢复节点使用。"""

        with self._locked_connection() as connection:
            row = connection.execute(
                """
                SELECT approval_id, call_id, session_id, tool_name, risk_level, arguments_json, status,
                       created_at, updated_at, expires_at
                FROM tool_approvals WHERE call_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (call_id,),
            ).fetchone()
        if row is None:
            raise ToolPolicyError("审批请求不存在", "APPROVAL_NOT_FOUND", 404)
        return self._approval_from_row(row)

    def list_audit(self, limit: int = 100) -> list[ToolAuditRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT audit_id, call_id, session_id, speaker_identity, tool_name, risk_level,
                       approval, status, arguments_summary, result_summary, error_code, created_at
                FROM tool_audit
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [self._audit_from_row(row) for row in rows]

    def execute(
        self,
        request: ToolExecuteRequest,
        identity: IdentitySnapshot,
        call_id: str | None = None,
    ) -> ToolCallResult:
        definition = self._definition(request.tool_name)
        if not definition.enabled:
            raise ToolPolicyError(
                definition.unavailable_reason or "工具当前不可用",
                "TOOL_NOT_CONFIGURED",
                503,
            )
        if definition.risk_level == "high":
            raise ToolPolicyError("高风险工具默认关闭", "HIGH_RISK_TOOL_DISABLED", 403)
        if definition.requires_owner and not identity.can_use_tools:
            raise ToolPolicyError("请先完成主人身份验证", "OWNER_VERIFICATION_REQUIRED", 403)

        if call_id is None:
            call_id = f"tool_{uuid4().hex}"
        elif not re.fullmatch(r"tool_[a-f0-9]{32}", call_id):
            raise ToolPolicyError("工具调用标识无效", "INVALID_CALL_ID", 400)
        now = _timestamp()
        arguments = self._validate_arguments(definition.name, request.arguments)
        if definition.requires_confirmation:
            approval_id = f"approval_{uuid4().hex}"
            expires_at = _timestamp_from_epoch(_epoch() + APPROVAL_TTL_SECONDS)
            audit_id = self._insert_audit(
                call_id=call_id,
                session_id=request.session_id,
                identity=identity,
                tool_name=definition.name,
                risk_level=definition.risk_level,
                approval="pending",
                status="pending",
                arguments=arguments,
                result_summary=None,
                error_code=None,
                created_at=now,
            )
            with self._locked_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO tool_approvals (
                        approval_id, call_id, session_id, tool_name, risk_level, arguments_json, status,
                        created_at, updated_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        approval_id,
                        call_id,
                        request.session_id,
                        definition.name,
                        definition.risk_level,
                        json.dumps(arguments, ensure_ascii=False, sort_keys=True),
                        "pending",
                        now,
                        now,
                        expires_at,
                    ),
                )
            return ToolCallResult(
                call_id=call_id,
                tool_name=definition.name,
                risk_level=definition.risk_level,
                status="pending",
                approval="pending",
                requires_confirmation=True,
                audit_id=audit_id,
                created_at=now,
            )

        return self._run(
            call_id=call_id,
            session_id=request.session_id,
            identity=identity,
            definition=definition,
            arguments=arguments,
            approval="auto_approved",
            audit_id=None,
            created_at=now,
        )

    def approve(self, approval_id: str, identity: IdentitySnapshot) -> ToolCallResult:
        if not identity.can_use_tools:
            raise ToolPolicyError("请先完成主人身份验证", "OWNER_VERIFICATION_REQUIRED", 403)
        with self._locked_connection() as connection:
            row = connection.execute(
                """
                SELECT approval_id, call_id, session_id, tool_name, risk_level, arguments_json, status,
                       created_at, updated_at, expires_at
                FROM tool_approvals WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
            if row is None:
                raise ToolPolicyError("审批请求不存在", "APPROVAL_NOT_FOUND", 404)
            approval = self._approval_from_row(row)
            if approval.status != "pending":
                raise ToolPolicyError("审批请求已处理", "APPROVAL_ALREADY_RESOLVED", 409)
            if _parse_timestamp(approval.expires_at) <= _epoch():
                connection.execute(
                    "UPDATE tool_approvals SET status = ?, updated_at = ? WHERE approval_id = ?",
                    ("expired", _timestamp(), approval_id),
                )
                expired = True
            else:
                expired = False
            if not expired:
                connection.execute(
                    "UPDATE tool_approvals SET status = ?, updated_at = ? WHERE approval_id = ?",
                    ("approved", _timestamp(), approval_id),
                )
        if expired:
            raise ToolPolicyError("审批请求已过期", "APPROVAL_EXPIRED", 409)

        definition = self._definition(approval.tool_name)
        arguments = self._validate_arguments(approval.tool_name, approval.arguments)
        return self._run(
            call_id=approval.call_id,
            session_id=approval.session_id,
            identity=identity,
            definition=definition,
            arguments=arguments,
            approval="approved",
            audit_id=self._audit_id_for_call(approval.call_id),
            created_at=approval.created_at,
        )

    def reject(self, approval_id: str, identity: IdentitySnapshot) -> ToolCallResult:
        if not identity.can_use_tools:
            raise ToolPolicyError("请先完成主人身份验证", "OWNER_VERIFICATION_REQUIRED", 403)
        with self._locked_connection() as connection:
            row = connection.execute(
                """
                SELECT approval_id, call_id, session_id, tool_name, risk_level, arguments_json, status,
                       created_at, updated_at, expires_at
                FROM tool_approvals WHERE approval_id = ?
                """,
                (approval_id,),
            ).fetchone()
            if row is None:
                raise ToolPolicyError("审批请求不存在", "APPROVAL_NOT_FOUND", 404)
            approval = self._approval_from_row(row)
            if approval.status != "pending":
                raise ToolPolicyError("审批请求已处理", "APPROVAL_ALREADY_RESOLVED", 409)
            now = _timestamp()
            connection.execute(
                "UPDATE tool_approvals SET status = ?, updated_at = ? WHERE approval_id = ?",
                ("rejected", now, approval_id),
            )
        audit_id = self._audit_id_for_call(approval.call_id)
        self._update_audit(
            audit_id,
            approval="rejected",
            status="rejected",
            result_summary="用户拒绝执行",
            error_code="APPROVAL_REJECTED",
        )
        return ToolCallResult(
            call_id=approval.call_id,
            tool_name=approval.tool_name,
            risk_level=approval.risk_level,
            status="rejected",
            approval="rejected",
            requires_confirmation=True,
            error_code="APPROVAL_REJECTED",
            error_message="用户拒绝执行",
            audit_id=audit_id,
            created_at=approval.created_at,
        )

    def _run(
        self,
        *,
        call_id: str,
        session_id: str,
        identity: IdentitySnapshot,
        definition: ToolDefinition,
        arguments: dict[str, Any],
        approval: ApprovalState,
        audit_id: str | None,
        created_at: str,
    ) -> ToolCallResult:
        if audit_id is None:
            audit_id = self._insert_audit(
                call_id=call_id,
                session_id=session_id,
                identity=identity,
                tool_name=definition.name,
                risk_level=definition.risk_level,
                approval=approval,
                status="pending",
                arguments=arguments,
                result_summary=None,
                error_code=None,
                created_at=created_at,
            )
        try:
            result = self._execute_tool(definition.name, arguments)
        except ToolPolicyError as exc:
            self._update_audit(
                audit_id,
                approval=approval,
                status="failure",
                result_summary=None,
                error_code=exc.code,
            )
            return ToolCallResult(
                call_id=call_id,
                tool_name=definition.name,
                risk_level=definition.risk_level,
                status="failure",
                approval=approval,
                requires_confirmation=definition.requires_confirmation,
                error_code=exc.code,
                error_message=str(exc),
                audit_id=audit_id,
                created_at=created_at,
            )
        except OSError as exc:
            self._update_audit(
                audit_id,
                approval=approval,
                status="failure",
                result_summary=None,
                error_code="OS_ERROR",
            )
            return ToolCallResult(
                call_id=call_id,
                tool_name=definition.name,
                risk_level=definition.risk_level,
                status="failure",
                approval=approval,
                requires_confirmation=definition.requires_confirmation,
                error_code="OS_ERROR",
                error_message=f"系统操作失败：{exc}",
                audit_id=audit_id,
                created_at=created_at,
            )
        self._update_audit(
            audit_id,
            approval=approval,
            status="success",
            result_summary=_summarize(result),
            error_code=None,
        )
        return ToolCallResult(
            call_id=call_id,
            tool_name=definition.name,
            risk_level=definition.risk_level,
            status="success",
            approval=approval,
            requires_confirmation=definition.requires_confirmation,
            result=result,
            audit_id=audit_id,
            created_at=created_at,
        )

    def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "get_time":
            now = datetime.now().astimezone()
            return {
                "iso": now.isoformat(),
                "date": now.date().isoformat(),
                "time": now.strftime("%H:%M:%S"),
                "timezone": str(now.tzinfo),
            }
        if tool_name == "search_files":
            root = self._authorized_path(arguments["root_path"], must_exist=True)
            if not root.is_dir():
                raise ToolValidationError("查找目录必须是文件夹")
            pattern = arguments["pattern"]
            matches: list[dict[str, Any]] = []
            for path in root.rglob(pattern):
                if len(matches) >= arguments["max_results"]:
                    break
                if path.is_symlink() or not path.is_file():
                    continue
                resolved = path.resolve()
                if not self._is_allowed_path(resolved):
                    continue
                stat = resolved.stat()
                matches.append({
                    "name": resolved.name,
                    "path": str(resolved),
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                })
            return {"root": str(root), "pattern": pattern, "count": len(matches), "files": matches}
        if tool_name == "open_application":
            app_name = arguments["app_name"]
            command = self.allowed_applications.get(app_name)
            if command is None:
                raise ToolPolicyError("应用不在白名单中", "APPLICATION_NOT_ALLOWED", 403)
            process = subprocess.Popen([command], close_fds=True)  # noqa: S603
            return {"app_name": app_name, "pid": process.pid}
        if tool_name == "open_file":
            path = self._authorized_path(arguments["path"], must_exist=True)
            if not path.is_file():
                raise ToolValidationError("只能打开文件")
            if os.name != "nt":
                raise ToolPolicyError("当前平台暂不支持打开文件", "PLATFORM_UNSUPPORTED", 501)
            os.startfile(str(path))  # type: ignore[attr-defined]
            return {"path": str(path), "opened": True}
        if tool_name == "control_music":
            action = arguments["action"]
            command = self.allowed_applications.get("QQ音乐")
            if command is None:
                raise ToolPolicyError("QQ音乐不在白名单中", "APPLICATION_NOT_ALLOWED", 403)
            running = self._find_application_windows(command)
            started = False
            if not running and action == "play":
                process = subprocess.Popen([command], close_fds=True)  # noqa: S603
                running = self._wait_for_application_window(command)
                started = True
                result_pid = process.pid
            else:
                result_pid = running[0][1] if running else None
            if not running:
                raise ToolPolicyError("QQ音乐尚未运行", "MUSIC_NOT_RUNNING", 409)
            self._send_music_play_pause(running[0][0])
            return {
                "app_name": "QQ音乐",
                "action": action,
                "started": started,
                "pid": result_pid,
                "window_title": running[0][2],
            }
        raise ToolPolicyError("工具未实现", "TOOL_NOT_IMPLEMENTED", 501)

    def _validate_arguments(self, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if tool_name == "get_time":
            if arguments:
                raise ToolValidationError("查询时间不接受参数")
            return {}
        if tool_name == "search_files":
            root_path = _required_string(arguments, "root_path", 512)
            pattern = _required_string(arguments, "pattern", 120)
            if "/" in pattern or "\\" in pattern or ".." in pattern:
                raise ToolValidationError("文件名匹配模式只能包含文件名，不允许路径跳转")
            max_results = arguments.get("max_results", 20)
            if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= MAX_SEARCH_RESULTS:
                raise ToolValidationError(f"max_results 必须是 1 到 {MAX_SEARCH_RESULTS} 的整数")
            return {"root_path": root_path, "pattern": pattern, "max_results": max_results}
        if tool_name == "open_application":
            app_name = _required_string(arguments, "app_name", 80)
            if app_name not in self.allowed_applications:
                raise ToolPolicyError("应用不在白名单中", "APPLICATION_NOT_ALLOWED", 403)
            return {"app_name": app_name}
        if tool_name == "open_file":
            return {"path": _required_string(arguments, "path", 512)}
        if tool_name == "control_music":
            action = _required_string(arguments, "action", 10).lower()
            if action not in {"play", "pause"}:
                raise ToolValidationError("音乐操作只能是 play 或 pause")
            return {"action": action}
        raise ToolPolicyError("工具不存在", "UNKNOWN_TOOL", 404)

    def _definition(self, tool_name: str) -> ToolDefinition:
        for definition in self.definitions():
            if definition.name == tool_name:
                return definition
        raise ToolPolicyError("工具不存在", "UNKNOWN_TOOL", 404)

    def _find_application_windows(self, command: str) -> list[tuple[int, int, str]]:
        """Return the allowlisted app's window, or its tray/background process."""

        executable_name = Path(command).name.casefold()
        windows: list[tuple[int, int, str]] = []

        if os.name != "nt":
            return windows

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            try:
                process_handle = kernel32.OpenProcess(0x1000, False, pid.value)
                path_buffer = ctypes.create_unicode_buffer(260)
                matched = False
                if process_handle:
                    size = wintypes.DWORD(260)
                    if kernel32.QueryFullProcessImageNameW(
                        process_handle, 0, path_buffer, ctypes.byref(size),
                    ):
                        matched = Path(path_buffer.value).name.casefold() == executable_name
                    kernel32.CloseHandle(process_handle)
                if matched:
                    windows.append((int(hwnd), int(pid.value), buffer.value))
            except OSError:
                pass
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        if windows:
            return windows

        # QQ Music can keep running from the tray without a visible top-level window.
        # Use the process list so playback control still works in that state.
        executable_name = Path(command).name
        process_command = (
            "$p = Get-Process -ErrorAction SilentlyContinue "
            f"-Name '{Path(executable_name).stem}'; "
            "if ($p) { $p | Select-Object -First 1 Id,ProcessName | ConvertTo-Json -Compress }"
        )
        process_result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", process_command],
            capture_output=True,
            text=True,
            check=False,
        )
        if process_result.returncode == 0 and process_result.stdout.strip():
            payload = json.loads(process_result.stdout)
            windows.append((0, int(payload["Id"]), str(payload["ProcessName"])))
        return windows

    def _wait_for_application_window(self, command: str) -> list[tuple[int, int, str]]:
        deadline_seconds = 8
        started = _epoch()
        while _epoch() - started < deadline_seconds:
            windows = self._find_application_windows(command)
            if windows:
                return windows

            import time

            time.sleep(0.25)
        return []

    def _send_music_play_pause(self, hwnd: int) -> None:
        user32 = ctypes.windll.user32
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.keybd_event.argtypes = [
            wintypes.BYTE,
            wintypes.BYTE,
            wintypes.DWORD,
            wintypes.ULONG,
        ]
        target_window = wintypes.HWND(hwnd)
        if hwnd:
            user32.ShowWindow(target_window, 9)  # SW_RESTORE
            user32.SetForegroundWindow(target_window)
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_KEYUP, 0)

    def _authorized_path(self, raw_path: str, *, must_exist: bool) -> Path:
        path = Path(raw_path).expanduser()
        try:
            resolved = path.resolve(strict=must_exist)
        except FileNotFoundError as exc:
            raise ToolValidationError("目标路径不存在", "PATH_NOT_FOUND") from exc
        if not self._is_allowed_path(resolved):
            raise ToolPolicyError("路径不在授权目录内", "PATH_NOT_ALLOWED", 403)
        return resolved

    def _is_allowed_path(self, path: Path) -> bool:
        return any(path == root or root in path.parents for root in self.allowed_directories)

    def _initialize(self) -> None:
        with self._locked_connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tool_approvals (
                    approval_id TEXT PRIMARY KEY,
                    call_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL DEFAULT 'tool-session',
                    tool_name TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tool_approvals_status
                    ON tool_approvals (status, created_at DESC);
                CREATE TABLE IF NOT EXISTS tool_audit (
                    audit_id TEXT PRIMARY KEY,
                    call_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    speaker_identity TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    approval TEXT NOT NULL,
                    status TEXT NOT NULL,
                    arguments_summary TEXT NOT NULL,
                    result_summary TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tool_audit_created_at
                    ON tool_audit (created_at DESC);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tool_approvals)").fetchall()
            }
            if "session_id" not in columns:
                connection.execute(
                    "ALTER TABLE tool_approvals ADD COLUMN session_id TEXT NOT NULL DEFAULT 'tool-session'"
                )

    def _insert_audit(
        self,
        *,
        call_id: str,
        session_id: str,
        identity: IdentitySnapshot,
        tool_name: str,
        risk_level: RiskLevel,
        approval: ApprovalState,
        status: ExecutionState,
        arguments: Mapping[str, Any],
        result_summary: str | None,
        error_code: str | None,
        created_at: str,
    ) -> str:
        audit_id = f"audit_{uuid4().hex}"
        with self._locked_connection() as connection:
            connection.execute(
                """
                INSERT INTO tool_audit (
                    audit_id, call_id, session_id, speaker_identity, tool_name, risk_level,
                    approval, status, arguments_summary, result_summary, error_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    call_id,
                    session_id,
                    identity.status,
                    tool_name,
                    risk_level,
                    approval,
                    status,
                    _summarize(dict(arguments)),
                    result_summary,
                    error_code,
                    created_at,
                ),
            )
        return audit_id

    def _update_audit(
        self,
        audit_id: str,
        *,
        approval: ApprovalState,
        status: ExecutionState,
        result_summary: str | None,
        error_code: str | None,
    ) -> None:
        with self._locked_connection() as connection:
            connection.execute(
                """
                UPDATE tool_audit
                SET approval = ?, status = ?, result_summary = ?, error_code = ?
                WHERE audit_id = ?
                """,
                (approval, status, result_summary, error_code, audit_id),
            )

    def _audit_id_for_call(self, call_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT audit_id FROM tool_audit WHERE call_id = ?",
                (call_id,),
            ).fetchone()
        if row is None:
            raise ToolPolicyError("工具审计记录不存在", "AUDIT_NOT_FOUND", 500)
        return str(row["audit_id"])

    @contextmanager
    def _locked_connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            with self._connect() as connection:
                yield connection

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _approval_from_row(row: sqlite3.Row) -> ToolApproval:
        return ToolApproval(
            approval_id=row["approval_id"],
            call_id=row["call_id"],
            session_id=row["session_id"],
            tool_name=row["tool_name"],
            risk_level=row["risk_level"],
            arguments=json.loads(row["arguments_json"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
        )

    @staticmethod
    def _audit_from_row(row: sqlite3.Row) -> ToolAuditRecord:
        return ToolAuditRecord(
            audit_id=row["audit_id"],
            call_id=row["call_id"],
            session_id=row["session_id"],
            speaker_identity=row["speaker_identity"],
            tool_name=row["tool_name"],
            risk_level=row["risk_level"],
            approval=row["approval"],
            status=row["status"],
            arguments_summary=row["arguments_summary"],
            result_summary=row["result_summary"],
            error_code=row["error_code"],
            created_at=row["created_at"],
        )


def _required_string(arguments: Mapping[str, Any], name: str, max_length: int) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ToolValidationError(f"{name} 必须是字符串")
    value = value.strip()
    if not value:
        raise ToolValidationError(f"{name} 不能为空")
    if len(value) > max_length:
        raise ToolValidationError(f"{name} 超出长度限制")
    return value


def _summarize(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text[:1_000]


def _epoch() -> float:
    return datetime.now(UTC).timestamp()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _timestamp_from_epoch(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat()


def _parse_timestamp(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()
