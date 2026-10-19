"""Validated codec for the cross-platform Axral World Project v1 format.

Keep file-format parsing independent from Qt so the real save/load path can be
covered by unit tests without opening file dialogs.
"""
from __future__ import annotations

import math
from typing import Any

from .events import Effect, Event
from .models import LAYER_HIERARCHY, SCHEMA_VERSION

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



def _parse_event(item: dict[str, Any], index: int) -> Event:
    """Validate and normalize an Event using the same contract as the Web codec."""
    prefix = f"events[{index}]"
    event_id = item.get("id")
    timestamp = item.get("timestamp")
    event_type = item.get("type")
    if not isinstance(event_id, str):
        raise ValueError(f"{prefix}.idは文字列である必要があります。")
    if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)):
        raise ValueError(f"{prefix}.timestampは有限数である必要があります。")
    if not isinstance(event_type, str):
        raise ValueError(f"{prefix}.typeは文字列である必要があります。")

    participants = item.get("participants", [])
    if not isinstance(participants, list) or not all(
        isinstance(participant, str) for participant in participants
    ):
        raise ValueError(f"{prefix}.participantsは文字列配列である必要があります。")

    effects_data = item.get("effects", [])
    if not isinstance(effects_data, list):
        raise ValueError(f"{prefix}.effectsは配列である必要があります。")
    effects = []
    for effect_index, effect in enumerate(effects_data):
        effect_prefix = f"{prefix}.effects[{effect_index}]"
        if not isinstance(effect, dict) or not isinstance(effect.get("kind"), str):
            raise ValueError(f"{effect_prefix}.kindは文字列である必要があります。")
        target_id = effect.get("target_id")
        if target_id is not None and not isinstance(target_id, str):
            raise ValueError(f"{effect_prefix}.target_idは文字列またはnullである必要があります。")
        effect_payload = effect.get("payload", {})
        if not isinstance(effect_payload, dict):
            raise ValueError(f"{effect_prefix}.payloadはオブジェクトである必要があります。")
        effects.append(Effect(kind=effect["kind"], target_id=target_id, payload=effect_payload))

    snapshot = item.get("is_snapshot_point", False)
    if not isinstance(snapshot, bool):
        raise ValueError(f"{prefix}.is_snapshot_pointは真偽値である必要があります。")
    schema_version = item.get("schema_version", SCHEMA_VERSION)
    if (isinstance(schema_version, bool) or not isinstance(schema_version, int)):
        raise ValueError(f"{prefix}.schema_versionは整数である必要があります。")
    metadata = item.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"{prefix}.metadataはオブジェクトである必要があります。")

    return Event(
        id=event_id,
        timestamp=timestamp,
        type=event_type,
        participants=list(participants),
        effects=effects,
        is_snapshot_point=snapshot,
        schema_version=schema_version,
        metadata=metadata,
    )

def parse_project(payload: Any) -> dict[str, Any]:
    """Validate a decoded payload and return normalized values for application loading."""
    if not isinstance(payload, dict) or payload.get("format") != PROJECT_FORMAT:
        raise ValueError("Axral World Project形式ではありません。")
    schema_version = payload.get("schema_version")
    if (isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != PROJECT_SCHEMA_VERSION):
        raise ValueError(
            f"未対応のプロジェクトschema_versionです: {schema_version!r}"
        )
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError("textフィールドがありません。")

    if "events" not in payload:
        raise ValueError("eventsフィールドがありません。")
    events_data = payload["events"]
    if not isinstance(events_data, list):
        raise ValueError("eventsは配列である必要があります。")
    events = []
    for index, item in enumerate(events_data):
        if not isinstance(item, dict):
            raise ValueError(f"events[{index}]はオブジェクトである必要があります。")
        events.append(_parse_event(item, index))

    positions = payload.get("graph_positions", {})
    timeline_data = payload.get("timeline", {})
    ignored = payload.get("ignored_candidates", [])
    if not isinstance(positions, dict) or not isinstance(timeline_data, dict) or not isinstance(ignored, list):
        raise ValueError("プロジェクト内の状態データが不正です。")
    # Match the Web codec's tolerant normalization for optional timeline fields.
    mode = timeline_data.get("mode", False)
    if not isinstance(mode, bool):
        mode = False
    timestamp = timeline_data.get("timestamp", 0)
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
        timestamp = 0
    else:
        timestamp = int(timestamp)
    visible_layers = timeline_data.get("visible_layers")
    if isinstance(visible_layers, list):
        visible_layers = [layer for layer in visible_layers if isinstance(layer, str)]
    else:
        visible_layers = list(LAYER_HIERARCHY)
    timeline = {
        "mode": mode,
        "timestamp": timestamp,
        "visible_layers": visible_layers,
    }
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
