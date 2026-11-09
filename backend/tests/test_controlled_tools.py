from dataclasses import replace

import pytest

from backend.app.controlled_tools import (
    APPROVAL_TTL_SECONDS,
    ControlledToolService,
    ToolExecuteRequest,
    ToolPolicyError,
)
from backend.app.identity import IdentityService, MockVoiceprintAdapter


def identity(owner: bool = True):
    service = IdentityService(MockVoiceprintAdapter())
    if owner:
        import asyncio

        asyncio.run(service.verify(service.adapter.owner_sample))
    return service.snapshot()


def test_get_time_is_available_without_owner_verification(tmp_path):
    service = ControlledToolService(tmp_path / "tools.sqlite3")

    result = service.execute(ToolExecuteRequest(tool_name="get_time"), identity(False))

    assert result.status == "success"
    assert result.approval == "auto_approved"
    assert result.result and "time" in result.result
    assert service.list_audit()[0].tool_name == "get_time"


def test_file_tools_require_owner_and_stay_inside_allowlist(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "note.txt").write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")
    service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_directories=(allowed,),
    )

    with pytest.raises(ToolPolicyError) as denied:
        service.execute(
            ToolExecuteRequest(
                tool_name="search_files",
                arguments={"root_path": str(allowed), "pattern": "*.txt"},
            ),
            identity(False),
        )
    assert denied.value.code == "OWNER_VERIFICATION_REQUIRED"

    result = service.execute(
        ToolExecuteRequest(
            tool_name="search_files",
            arguments={"root_path": str(allowed), "pattern": "*.txt"},
        ),
        identity(True),
    )
    assert result.result and result.result["count"] == 1
    assert str(outside) not in str(result.result)

    path_denied = service.execute(
        ToolExecuteRequest(
            tool_name="search_files",
            arguments={"root_path": str(outside), "pattern": "*.txt"},
        ),
        identity(True),
    )
    assert path_denied.status == "failure"
    assert path_denied.error_code == "PATH_NOT_ALLOWED"


def test_application_allowlist_does_not_accept_arbitrary_commands(tmp_path, monkeypatch):
    service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_applications={"safe": "safe.exe"},
    )
    popen = monkeypatch.setattr(
        "backend.app.controlled_tools.subprocess.Popen",
        lambda command, close_fds: type("Process", (), {"pid": 42})(),
    )
    del popen

    result = service.execute(
        ToolExecuteRequest(tool_name="open_application", arguments={"app_name": "safe"}),
        identity(True),
    )
    assert result.result == {"app_name": "safe", "pid": 42}

    with pytest.raises(ToolPolicyError) as denied:
        service.execute(
            ToolExecuteRequest(
                tool_name="open_application",
                arguments={"app_name": "powershell -Command whoami"},
            ),
            identity(True),
        )
    assert denied.value.code == "APPLICATION_NOT_ALLOWED"


def test_music_control_validates_action_and_uses_qqmusic_window(tmp_path, monkeypatch):
    service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_applications={"QQ音乐": r"D:\QQMusic\QQMusic.exe"},
    )
    monkeypatch.setattr(service, "_find_application_windows", lambda command: [(100, 42, "QQ音乐")])
    sent = []
    monkeypatch.setattr(
        service,
        "_send_music_play_pause",
        lambda hwnd: sent.append(hwnd),
    )

    result = service.execute(
        ToolExecuteRequest(
            tool_name="control_music",
            arguments={"action": "pause"},
        ),
        identity(True),
    )

    assert result.status == "success"
    assert result.result == {
        "app_name": "QQ音乐",
        "action": "pause",
        "started": False,
        "pid": 42,
        "window_title": "QQ音乐",
    }
    assert sent == [100]

    with pytest.raises(ToolPolicyError) as invalid:
        service.execute(
            ToolExecuteRequest(tool_name="control_music", arguments={"action": "stop"}),
            identity(True),
        )
    assert invalid.value.code == "INVALID_TOOL_ARGUMENTS"


def test_music_play_starts_qqmusic_when_missing(tmp_path, monkeypatch):
    service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_applications={"QQ音乐": r"D:\QQMusic\QQMusic.exe"},
    )
    calls = {"count": 0}

    def fake_windows(command):
        calls["count"] += 1
        return [(101, 43, "QQ音乐")] if calls["count"] > 1 else []

    monkeypatch.setattr(service, "_find_application_windows", fake_windows)
    monkeypatch.setattr(service, "_wait_for_application_window", lambda command: [(101, 43, "QQ音乐")])
    monkeypatch.setattr(
        "backend.app.controlled_tools.subprocess.Popen",
        lambda command, close_fds: type("Process", (), {"pid": 43})(),
    )
    monkeypatch.setattr(service, "_send_music_play_pause", lambda hwnd: None)

    result = service.execute(
        ToolExecuteRequest(tool_name="control_music", arguments={"action": "play"}),
        identity(True),
    )

    assert result.status == "success"
    assert result.result["started"] is True
    assert result.result["pid"] == 43


def test_open_file_creates_approval_then_uses_original_session_id(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "note.txt"
    target.write_text("ok", encoding="utf-8")
    service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_directories=(allowed,),
    )
    monkeypatch.setattr("backend.app.controlled_tools.os.name", "nt")
    monkeypatch.setattr("backend.app.controlled_tools.os.startfile", lambda path: None, raising=False)

    pending = service.execute(
        ToolExecuteRequest(
            tool_name="open_file",
            arguments={"path": str(target)},
            session_id="original-session",
        ),
        identity(True),
    )
    assert pending.status == "pending"
    approval = service.list_approvals()[0]
    assert approval.session_id == "original-session"

    approved = service.approve(approval.approval_id, identity(True))
    assert approved.status == "success"
    assert service.list_audit()[0].session_id == "original-session"


def test_reject_and_double_resolve_are_audited(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "note.txt"
    target.write_text("ok", encoding="utf-8")
    service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_directories=(allowed,),
    )
    pending = service.execute(
        ToolExecuteRequest(tool_name="open_file", arguments={"path": str(target)}),
        identity(True),
    )
    approval = service.list_approvals()[0]

    rejected = service.reject(approval.approval_id, identity(True))
    assert rejected.status == "rejected"
    assert service.list_audit()[0].error_code == "APPROVAL_REJECTED"

    with pytest.raises(ToolPolicyError) as already_resolved:
        service.reject(approval.approval_id, identity(True))
    assert already_resolved.value.code == "APPROVAL_ALREADY_RESOLVED"
    assert pending.call_id == rejected.call_id


def test_expired_approval_cannot_execute(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "note.txt"
    target.write_text("ok", encoding="utf-8")
    service = ControlledToolService(
        tmp_path / "tools.sqlite3",
        allowed_directories=(allowed,),
    )
    pending = service.execute(
        ToolExecuteRequest(tool_name="open_file", arguments={"path": str(target)}),
        identity(True),
    )
    approval = service.list_approvals()[0]
    monkeypatch.setattr(
        "backend.app.controlled_tools._epoch",
        lambda: __import__("time").time() + APPROVAL_TTL_SECONDS + 1,
    )

    with pytest.raises(ToolPolicyError) as expired:
        service.approve(approval.approval_id, identity(True))
    assert expired.value.code == "APPROVAL_EXPIRED"
    assert service.list_approvals(status="expired")[0].approval_id == approval.approval_id
    assert pending.status == "pending"


def test_high_risk_and_unknown_tools_are_denied(tmp_path):
    service = ControlledToolService(tmp_path / "tools.sqlite3")

    with pytest.raises(ToolPolicyError) as unknown:
        service.execute(ToolExecuteRequest(tool_name="run_shell"), identity(True))
    assert unknown.value.code == "UNKNOWN_TOOL"

    assert all(item.risk_level != "high" for item in service.definitions())
