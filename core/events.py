"""
Axral Codex - Event Schema (Phase 0b, §8)

plan.md (v2) §8, §14 に対応。

```
Event
 ├─ id
 ├─ timestamp
 ├─ type
 ├─ participants[]
 ├─ effects[]
 └─ metadata
```

Eventは「World Stateをどう変化させるか」を宣言するデータであり、
実際の適用ロジックは core/world_state.py が担う (関心の分離)。

Effect (この実装での拡張): 1つのEventは複数のEffectを持ちうる。
Timeline Lens (§14) が変化対象として挙げる「所属・生死・Relation・Ownership・
Organization・World State」を汎用的に表現するため、Effectは
「対象(Entity or Relation) + 操作種別 + payload」という最小構成にしてある。

対応するEffect kind:
  - "relation_add"        : 新しいRelationを追加する (payload: source, target, type, status?)
  - "relation_status"      : 既存Relationのstatusを変更する (payload: relation_id, status)
  - "relation_end"         : 既存Relationにvalid_toを設定する (payload: relation_id, valid_to)
  - "entity_attribute"     : Entity.attributesの1キーを更新する (payload: entity_id, key, value)
  - "entity_existence"     : Entity.existenceを変更する (payload: entity_id, existence)
                              例: 生死判定 (§15.1 Temporal Contradiction Linterの土台)

Snapshot Point (§9.1.1) の判定に使う情報として、Eventは
`is_snapshot_point` (User-defined Key Event) と `type` (Tear/Chapter等の
自動トリガー種別) を持つ。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import SCHEMA_VERSION, new_id

# Event.type がこれらに該当する場合、自動的にSnapshot Pointとして扱う
# (§9.1.1: Tear / Major Event / Chapter boundary)
AUTO_SNAPSHOT_TYPES: set[str] = {"Tear", "Chapter", "MajorEvent"}


@dataclass
class Effect:
    kind: str
    target_id: Optional[str] = None  # Entity.id または Relation.id
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "target_id": self.target_id, "payload": self.payload}

    @staticmethod
    def from_dict(d: dict) -> "Effect":
        return Effect(kind=d["kind"], target_id=d.get("target_id"), payload=d.get("payload", {}))


@dataclass
class Event:
    id: str
    timestamp: int
    type: str
    participants: list[str] = field(default_factory=list)  # Entity.id のリスト
    effects: list[Effect] = field(default_factory=list)
    is_snapshot_point: bool = False  # User-defined Key Event (§9.1.1)
    schema_version: int = SCHEMA_VERSION
    metadata: dict = field(default_factory=dict)

    @property
    def triggers_snapshot(self) -> bool:
        """§9.1.1: Tear / Major Event / Chapter boundary / User-defined Key Event。"""
        return self.is_snapshot_point or self.type in AUTO_SNAPSHOT_TYPES

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "type": self.type,
            "participants": list(self.participants),
            "effects": [e.to_dict() for e in self.effects],
            "is_snapshot_point": self.is_snapshot_point,
            "schema_version": self.schema_version,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(d: dict) -> "Event":
        return Event(
            id=d["id"],
            timestamp=d["timestamp"],
            type=d["type"],
            participants=list(d.get("participants", [])),
            effects=[Effect.from_dict(e) for e in d.get("effects", [])],
            is_snapshot_point=d.get("is_snapshot_point", False),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            metadata=d.get("metadata", {}),
        )


def new_event(
    timestamp: int,
    type_: str,
    participants: Optional[list[str]] = None,
    effects: Optional[list[Effect]] = None,
    is_snapshot_point: bool = False,
    metadata: Optional[dict] = None,
) -> Event:
    return Event(
        id=new_id("evt"),
        timestamp=timestamp,
        type=type_,
        participants=participants or [],
        effects=effects or [],
        is_snapshot_point=is_snapshot_point,
        metadata=metadata or {},
    )
