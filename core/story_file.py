"""Standalone filesystem helpers for *.axral-story.json.

These functions intentionally do not call or modify the existing world-project
save/load/recovery/export pipeline.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .story import parse_story, serialize_story

STORY_FILE_SUFFIX = ".axral-story.json"


def _story_path(path: str | os.PathLike[str]) -> Path:
    target = Path(path)
    if not str(target).lower().endswith(STORY_FILE_SUFFIX):
        raise ValueError(f"物語ファイルは {STORY_FILE_SUFFIX} で終わる必要があります。")
    return target


def load_story_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load and validate a standalone story file without touching project files."""
    target = _story_path(path)
    try:
        text = target.read_text(encoding="utf-8")
        payload = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"物語ファイルを読み込めませんでした: {exc}") from exc
    return parse_story(payload)


def save_story_file(path: str | os.PathLike[str], payload: Any) -> Path:
    """Validate and atomically save a standalone story file.

    Validation occurs before any file is created or replaced. The temporary
    file is placed in the destination directory so os.replace stays atomic
    on the same filesystem.
    """
    target = _story_path(path)
    serialized = serialize_story(payload)
    parent = target.parent
    if not parent.exists() or not parent.is_dir():
        raise ValueError("保存先フォルダーが存在しません。")
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=parent,
            prefix=f".{target.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temp_name = stream.name
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
        temp_name = None
    except OSError as exc:
        raise ValueError(f"物語ファイルを保存できませんでした: {exc}") from exc
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
    return target
