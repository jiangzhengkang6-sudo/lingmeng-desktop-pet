import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.app.local_state import (
    DesktopSettingsUpdate,
    LocalStateStore,
    ReminderCreateRequest,
    ReminderDispatcher,
    ReminderUpdateRequest,
)


def future_timestamp(minutes: int = 5) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def test_reminders_persist_and_can_be_updated_or_cancelled(tmp_path) -> None:
    database = tmp_path / "desktop-pet.sqlite3"
    store = LocalStateStore(database)
    reminder = store.create_reminder(ReminderCreateRequest(
        title="  喝水  ",
        remindAt=future_timestamp(),
        sessionId="session-a",
    ))

    assert reminder.title == "喝水"
    assert LocalStateStore(database).list_reminders()[0].id == reminder.id

    updated = store.update_reminder(reminder.id, ReminderUpdateRequest(title="站起来活动"))
    assert updated is not None
    assert updated.title == "站起来活动"
    assert store.cancel_reminder(reminder.id) is True
    assert store.list_reminders()[0].status == "cancelled"
    assert [log.event_type for log in store.list_logs()] == [
        "reminder.cancelled",
        "reminder.updated",
        "reminder.created",
    ]


def test_reminder_time_requires_timezone_and_future_date() -> None:
    with pytest.raises(ValueError):
        ReminderCreateRequest(title="测试", remindAt="2026-09-09T12:00:00")
    with pytest.raises(ValueError):
        ReminderCreateRequest(title="测试", remindAt="2020-01-01T00:00:00+00:00")


def test_due_reminders_dispatch_a_pet_action_once(tmp_path) -> None:
    store = LocalStateStore(tmp_path / "desktop-pet.sqlite3")
    reminder = store.create_reminder(ReminderCreateRequest(
        title="测试提醒",
        remindAt=future_timestamp(),
    ))
    due = datetime.now(UTC) + timedelta(minutes=10)
    assert [item.id for item in store.claim_due_reminders(due)] == [reminder.id]
    assert store.claim_due_reminders(due) == []

    due_reminder = store.create_reminder(ReminderCreateRequest(
        title="第二个测试提醒",
        remindAt=future_timestamp(),
    ))
    broadcast = AsyncMock(return_value=1)
    dispatcher = ReminderDispatcher(store, broadcast)
    due_time = datetime.now(UTC) + timedelta(minutes=10)
    assert asyncio.run(dispatcher.dispatch_due(due_time)) == 1
    broadcast.assert_awaited_once()
    assert broadcast.await_args.args[0].action_id == "reminder"
    assert asyncio.run(dispatcher.dispatch_due(due_time)) == 0
    fired = {item.id for item in store.list_reminders(status="fired")}
    assert due_reminder.id in fired


def test_settings_are_persisted_and_permission_mode_is_not_mutable(tmp_path) -> None:
    database = tmp_path / "desktop-pet.sqlite3"
    store = LocalStateStore(database)
    defaults = store.get_settings()
    assert defaults.permission_mode == "owner_confirmation"

    updated = store.update_settings(DesktopSettingsUpdate(
        language="ja-JP",
        personality="concise",
        diagnostics_enabled=False,
    ))
    assert updated.language == "ja-JP"
    assert updated.permission_mode == "owner_confirmation"
    assert LocalStateStore(database).get_settings().diagnostics_enabled is False
    assert store.list_logs()[0].event_type == "settings.updated"


def test_identity_system_events_are_safe_and_visible(tmp_path) -> None:
    store = LocalStateStore(tmp_path / "desktop-pet.sqlite3")

    store.record_system_event(
        category="identity",
        event_type="identity.voiceprint_registered",
        status="success",
        message="RTC 声纹注册完成，原始音频未落盘",
    )

    logs = store.list_logs()
    assert logs[0].category == "identity"
    assert logs[0].message == "RTC 声纹注册完成，原始音频未落盘"
    assert "secret" not in logs[0].message.lower()
    assert "voiceprint" not in logs[0].message.lower()
