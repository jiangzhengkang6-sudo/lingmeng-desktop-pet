from __future__ import annotations

import json
import subprocess
import sys

from scripts.inspect_rtc_event import describe_shape, load_event


def test_inspector_reports_paths_and_types_without_values() -> None:
    lines = describe_shape({
        "Result": {
            "TaskId": "task-secret",
            "VoicePrint": {"Name": "desktop-owner", "Score": 88},
        },
        "Transcript": "不要输出这段内容",
    })

    assert "$: object" in lines
    assert "$/Result/TaskId: string" in lines
    assert "$/Result/VoicePrint/Score: number" in lines
    assert all("task-secret" not in line for line in lines)
    assert all("desktop-owner" not in line for line in lines)
    assert all("不要输出" not in line for line in lines)


def test_inspector_loads_json_but_does_not_require_provider_fields() -> None:
    event = load_event(json.dumps({"unknown": [{"value": 1}]}))

    assert event == {"unknown": [{"value": 1}]}


def test_inspector_cli_reads_file_and_never_submits_event(tmp_path) -> None:
    event_path = tmp_path / "rtc-event.json"
    event_path.write_text(
        json.dumps({"TaskId": "task-secret", "Score": 88}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/inspect_rtc_event.py", "--input-file", str(event_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "$/TaskId: string" in result.stdout
    assert "task-secret" not in result.stdout
    assert "voiceprint-observations" not in result.stdout
