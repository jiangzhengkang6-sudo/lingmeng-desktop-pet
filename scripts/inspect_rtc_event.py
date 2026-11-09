from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import Any, TextIO


MAX_INPUT_BYTES = 1_000_000
MAX_DEPTH = 12
MAX_ITEMS_PER_OBJECT = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="仅输出 RTC 回调 JSON 的字段路径和类型，不输出字段值，也不会提交身份网关。",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="RTC 回调 JSON 文件；未提供时从标准输入读取",
    )
    return parser.parse_args()


def read_input(stream: TextIO) -> str:
    content = stream.read(MAX_INPUT_BYTES + 1)
    if len(content.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("输入 JSON 超过 1 MB")
    return content


def load_event(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("输入不是有效 JSON") from exc


def describe_shape(value: Any, path: str = "$", depth: int = 0) -> list[str]:
    if depth > MAX_DEPTH:
        return [f"{path}: depth-limit"]
    if value is None:
        return [f"{path}: null"]
    if isinstance(value, bool):
        return [f"{path}: boolean"]
    if isinstance(value, str):
        return [f"{path}: string"]
    if isinstance(value, (int, float)):
        return [f"{path}: number"]
    if isinstance(value, Mapping):
        lines = [f"{path}: object"]
        items = list(value.items())
        for key, child in items[:MAX_ITEMS_PER_OBJECT]:
            safe_key = str(key).replace("~", "~0").replace("/", "~1")
            lines.extend(describe_shape(child, f"{path}/{safe_key}", depth + 1))
        if len(items) > MAX_ITEMS_PER_OBJECT:
            lines.append(f"{path}: omitted-object-fields")
        return lines
    if isinstance(value, Sequence):
        lines = [f"{path}: array"]
        for index, child in enumerate(value[:MAX_ITEMS_PER_OBJECT]):
            lines.extend(describe_shape(child, f"{path}/{index}", depth + 1))
        if len(value) > MAX_ITEMS_PER_OBJECT:
            lines.append(f"{path}: omitted-array-items")
        return lines
    return [f"{path}: unsupported"]


def main() -> int:
    args = parse_args()
    input_stream: TextIO = sys.stdin
    should_close = False
    if args.input_file:
        try:
            input_stream = args.input_file.open("r", encoding="utf-8")
        except OSError as exc:
            print(f"无法打开输入文件：{args.input_file}", file=sys.stderr)
            return 1
        should_close = True

    try:
        try:
            event = load_event(read_input(input_stream))
        except (OSError, UnicodeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        for line in describe_shape(event):
            print(line)
        return 0
    finally:
        if should_close:
            input_stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
