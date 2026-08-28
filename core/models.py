"""
Axral Codex - Canonical Data Model (Phase 0a: MVP1 Minimal Schema)

plan.md (v2) の設計に対応:
  - Entity / Relation は Stable ID を持つ (§6, §7)
  - schema_version フィールドで将来のマイグレーションに備える (§18.8)
  - Relation.perspective は Reality vs Knowledge (§7.2.1) の拡張ポイント
    (MVP1では常に "objective" 固定。実装はPhase 3で行う)
  - source_refs[] により、どの行から生成されたデータかを追跡する (§6, §7)

このモジュールはSource of Truth (Canonical Data)そのものであり、
UI (Editor/Graph View) はここを介してのみデータを読み書きする (§3)。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

SCHEMA_VERSION = 1


def new_id(prefix: str) -> str:
    """Stable ID生成。プレフィックス付きUUID4。"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class SourceRef:
    """このEntity/Relationがどの行・どの記述から生成されたかを追跡する。"""
    line: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Entity:
    id: str
    type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    layer: Optional[str] = None
    attributes: dict = field(default_factory=dict)
    existence: str = "confirmed"  # confirmed / hypothetical / rumor (§7.1と同じ語彙を流用)
    source_refs: list[SourceRef] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_refs"] = [r.to_dict() for r in self.source_refs]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Entity":
        d = dict(d)
        d["source_refs"] = [SourceRef(**r) for r in d.get("source_refs", [])]
        return Entity(**d)


@dataclass
class Relation:
    id: str
    source: str  # Entity.id
    target: str  # Entity.id
    type: str
    status: str = "confirmed"  # confirmed / hypothetical / rumor (§7.1)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    perspective: str = "objective"  # Reality vs Knowledge拡張点 (§7.2.1)
    source_refs: list[SourceRef] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_refs"] = [r.to_dict() for r in self.source_refs]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Relation":
        d = dict(d)
        d["source_refs"] = [SourceRef(**r) for r in d.get("source_refs", [])]
        return Relation(**d)


class WorldModel:
    """
    Canonical Data Model本体 (Phase 0a scope: Entity + Relation のみ。
    Event / World State / Snapshot は Phase 0b / Phase 3 で追加)。

    Editor/Canvas/Timelineは全てこのクラスを介してデータを読み書きする (§3)。
    """

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.relations: dict[str, Relation] = {}
        # name -> entity_id の索引。MVP1では単純な名前一致で解決する。
        # (本格的なAmbiguity Resolution §5 はPhase 1.5のSecondary Indexerで行う)
        self._name_index: dict[str, str] = {}

    # ---- Entity operations -------------------------------------------------

    def get_or_create_entity(
        self, name: str, type_: Optional[str], source_ref: SourceRef
    ) -> Entity:
        """
        名前でEntityを検索し、なければ新規作成する。

        既存Entityにtype_が指定され、既存のtypeが"Unknown"だった場合はtypeを確定させる。
        これは「曖昧な自然言語→明示構文への昇格」(§5.3)の最小版に相当する:
        先に shorthand (`A -> B : rel`) で Unknown 型として生成された Entity を、
        後から `[A:Character]` の明示宣言で型確定させられる。
        """
        existing_id = self._name_index.get(name)
        if existing_id is not None:
            entity = self.entities[existing_id]
            if type_ and entity.type == "Unknown":
                entity.type = type_
            entity.source_refs.append(source_ref)
            return entity

        entity = Entity(
            id=new_id("ent"),
            type=type_ or "Unknown",
            name=name,
            source_refs=[source_ref],
        )
        self.entities[entity.id] = entity
        self._name_index[name] = entity.id
        return entity

    # ---- Relation operations ------------------------------------------------

    def add_relation(
        self, source_id: str, target_id: str, rel_type: str, source_ref: SourceRef
    ) -> Relation:
        """
        Relationを追加する。

        MVP1では重複判定は行わず単純追加とする。重複統合・Conflict検出は
        Phase 2 (Non-destructive Text Sync / Conflict UI, §11) で扱う。
        """
        relation = Relation(
            id=new_id("rel"),
            source=source_id,
            target=target_id,
            type=rel_type,
            source_refs=[source_ref],
        )
        self.relations[relation.id] = relation
        return relation

    # ---- Serialization --------------------------------------------------

    def to_json(self) -> str:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "entities": [e.to_dict() for e in self.entities.values()],
            "relations": [r.to_dict() for r in self.relations.values()],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(text: str) -> "WorldModel":
        payload = json.loads(text)
        model = WorldModel()
        for ed in payload.get("entities", []):
            entity = Entity.from_dict(ed)
            model.entities[entity.id] = entity
            model._name_index[entity.name] = entity.id
        for rd in payload.get("relations", []):
            relation = Relation.from_dict(rd)
            model.relations[relation.id] = relation
        return model

    def clear(self) -> None:
        self.entities.clear()
        self.relations.clear()
        self._name_index.clear()
