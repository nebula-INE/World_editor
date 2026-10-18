"""Validated codec for the cross-platform Axral World Project v1 format.

Keep file-format parsing independent from Qt so the real save/load path can be
covered by unit tests without opening file dialogs.
"""
from __future__ import annotations

import math
from typing import Any

from .events import Event

PROJECT_FORMAT = "axral-world-project"
PROJECT_SCHEMA_VERSION = 1


def build_project(
    text: str,
    events: list[Event],
    graph_positions: dict[str, Any],
    timeline: dict[str, Any],
    ignored_candidates: list[list[Any]],
) -> dict[str, Any]:
    """Build a JSON-ready project payload using the canonical v1 field names."""
    if not isinstance(text, str):
        raise ValueError("textは文字列である必要があります。")
    return {
        "format": PROJECT_FORMAT,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "text": text,
        "events": [event.to_dict() for event in events],
        "graph_positions": graph_positions,
        "timeline": timeline,
        "ignored_candidates": [list(signature) for signature in ignored_candidates],
    }


def parse_project(payload: Any) -> dict[str, Any]:
    """Validate a decoded payload and return normalized values for application loading."""
    if not isinstance(payload, dict) or payload.get("format") != PROJECT_FORMAT:
        raise ValueError("Axral World Project形式ではありません。")
    if payload.get("schema_version") != PROJECT_SCHEMA_VERSION:
        raise ValueError(
            f"未対応のプロジェクトschema_versionです: {payload.get('schema_version')!r}"
        )
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError("textフィールドがありません。")

    events_data = payload.get("events", [])
    if not isinstance(events_data, list):
        raise ValueError("eventsは配列である必要があります。")
    events = []
    for index, item in enumerate(events_data):
        if not isinstance(item, dict):
            raise ValueError(f"events[{index}]はオブジェクトである必要があります。")
        events.append(Event.from_dict(item))

    positions = payload.get("graph_positions", {})
    timeline = payload.get("timeline", {})
    ignored = payload.get("ignored_candidates", [])
    if not isinstance(positions, dict) or not isinstance(timeline, dict) or not isinstance(ignored, list):
        raise ValueError("プロジェクト内の状態データが不正です。")
    for entity_id, point in positions.items():
        if not isinstance(entity_id, str) or not isinstance(point, dict):
            raise ValueError("graph_positionsの形式が不正です。")
        for axis in ("x", "y"):
            value = point.get(axis)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"graph_positions.{entity_id}.{axis}は有限数である必要があります。")

    normalized_ignored = []
    for signature in ignored:
        if (isinstance(signature, list) and len(signature) == 4
                and isinstance(signature[0], int) and not isinstance(signature[0], bool)
                and all(isinstance(part, str) for part in signature[1:])):
            normalized_ignored.append(tuple(signature))
    return {
        "text": text,
        "events": events,
        "graph_positions": positions,
        "timeline": timeline,
        "ignored_candidates": normalized_ignored,
    }
