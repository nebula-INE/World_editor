"""
Axral Codex - Canonical Data Model (Phase 0a/0b: Entity / Relation / Reference System)

plan.md (v2) の設計に対応:
  - Entity / Relation は Stable ID を持つ (§6, §7)
  - schema_version フィールドで将来のマイグレーションに備える (§18.8)
  - Relation.perspective は Reality vs Knowledge (§7.2.1) の拡張ポイント
    (MVP1では常に "objective" 固定。実装はPhase 3で行う)
  - source_refs[] により、どの行から生成されたデータかを追跡する (§6, §7)
  - aliases[] / WorldModel.resolve() により Reference System を提供する (Phase 0b)
  - LAYER_HIERARCHY により Layer System (§13) の階層を定義する (Phase 0b。
    Layer Sliderなどの操作UIはPhase 3で実装)

このモジュールはSource of Truth (Canonical Data)そのものであり、
UI (Editor/Graph View) はここを介してのみデータを読み書きする (§3)。

Event / World State / Snapshot は core/events.py, core/world_state.py
(いずれもPhase 0b) が、このモジュールの WorldModel を Initial State として
参照する形で実装する (§8, §9)。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

SCHEMA_VERSION = 1

# Layer System (§13) の階層定義。
# Layer Slider (Phase 3, §13) はこの順序をもとにHighlight/Filteringを行う予定。
# ここではPhase 0bの一部として「階層そのもの」だけを定義し、UI操作は実装しない。
LAYER_HIERARCHY: list[str] = ["Su-ken", "Kan-ken", "An-ken", "Ki-ken"]


def is_valid_layer(layer: Optional[str]) -> bool:
    return layer is None or layer in LAYER_HIERARCHY


def new_id(prefix: str) -> str:
    """Stable ID生成。プレフィックス付きUUID4。"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def stable_entity_id(name: str) -> str:
    """
    Entity名から決定論的に導出したStable ID (Phase 2)。

    MVP1では new_id() によるランダムUUIDを使っていたが、全文を毎回
    再解析するMVP1の実装 (§12.1 Incremental Parsingは未実装) では
    同じEntityでも再解析のたびにIDが変わってしまい、Canvas由来のPatch
    (§10.2) が特定のEntity/Relationを安定して参照できなかった。
    名前からのハッシュに切り替えることで、同じ名前のEntityは常に同じIDになる。
    """
    return "ent_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


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
    # Patch (§10.2) が参照するための人間可読な安定キー。
    # "SourceName->TargetName#n" 形式 (nはそのペアの中での出現順、0始まり)。
    # typeなど可変フィールドとは独立して、出現位置(行)に紐づく識別子とする。
    ref_key: Optional[str] = None
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
    Canonical Data Model本体。

    Phase 0a scope: Entity + Relation (+ Reference System / Alias解決, Phase 0b)。
    Event / World State / Snapshot は別モジュール core/events.py, core/world_state.py
    (Phase 0b) が WorldModel を Initial State として参照する形で実装する。

    Editor/Canvas/Timelineは全てこのクラスを介してデータを読み書きする (§3)。
    """

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.relations: dict[str, Relation] = {}
        # name -> entity_id の索引。MVP1では単純な名前一致で解決する。
        # (本格的なAmbiguity Resolution §5 はPhase 1.5のSecondary Indexerで行う)
        self._name_index: dict[str, str] = {}
        # alias -> entity_id の索引 (Reference System, Phase 0b)。
        # nameとは別テーブルにして、"名前としての一意性"と"別名としての一意性"を混同しない。
        self._alias_index: dict[str, str] = {}
        # (source_id, target_id) ペアごとの出現回数カウンタ。ref_key採番に使う (Phase 2)。
        self._pair_occurrence: dict[str, int] = {}
        # ref_key -> relation_id の索引 (Phase 2, Patchの参照解決に使う)。
        self._ref_key_index: dict[str, str] = {}

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
            id=stable_entity_id(name),
            type=type_ or "Unknown",
            name=name,
            source_refs=[source_ref],
        )
        self.entities[entity.id] = entity
        self._name_index[name] = entity.id
        return entity

    # ---- Reference System (Phase 0b, §6 aliases[]) --------------------------

    def add_alias(self, entity_id: str, alias: str) -> None:
        """
        Entityにaliasを追加する。同じaliasが既に別Entityに登録されている場合は
        エラーにせず無視する (Silent Guessをしないのと同様、勝手な上書きもしない。
        Alias衝突の解消はPhase 1.5 Ambiguity Resolution §5の対象)。
        """
        entity = self.entities.get(entity_id)
        if entity is None:
            return
        if alias in self._alias_index and self._alias_index[alias] != entity_id:
            return
        if alias not in entity.aliases:
            entity.aliases.append(alias)
        self._alias_index[alias] = entity_id

    def resolve(self, name_or_alias: str) -> Optional[Entity]:
        """
        名前またはAliasからEntityを解決する (Reference System)。
        まずnameで検索し、見つからなければaliasで検索する。
        """
        entity_id = self._name_index.get(name_or_alias) or self._alias_index.get(name_or_alias)
        if entity_id is None:
            return None
        return self.entities.get(entity_id)

    # ---- Relation operations ------------------------------------------------

    def add_relation(
        self, source_id: str, target_id: str, rel_type: str, source_ref: SourceRef
    ) -> Relation:
        """
        Relationを追加する。

        MVP1では重複判定は行わず単純追加とする。重複統合・Conflict検出は
        Phase 2 (Non-destructive Text Sync / Conflict UI, §11) で扱う。

        ref_key (Phase 2追加): 同じ (source, target) の中での出現順に基づく
        人間可読な安定キー ("SourceName->TargetName#n")。Patchはこのキーで
        Relationを参照する — typeを書き換えてもref_keyは変わらない。
        """
        pair_key = f"{source_id}->{target_id}"
        n = self._pair_occurrence.get(pair_key, 0)
        self._pair_occurrence[pair_key] = n + 1

        source_name = self.entities[source_id].name if source_id in self.entities else source_id
        target_name = self.entities[target_id].name if target_id in self.entities else target_id
        ref_key = f"{source_name}->{target_name}#{n}"

        relation = Relation(
            id=new_id("rel"),
            source=source_id,
            target=target_id,
            type=rel_type,
            ref_key=ref_key,
            source_refs=[source_ref],
        )
        self.relations[relation.id] = relation
        self._ref_key_index[ref_key] = relation.id
        return relation

    def find_by_ref_key(self, ref_key: str) -> Optional[Relation]:
        """Patch (§10.2) がRelationを参照するためのルックアップ。"""
        relation_id = self._ref_key_index.get(ref_key)
        if relation_id is None:
            return None
        return self.relations.get(relation_id)

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
            for alias in entity.aliases:
                model._alias_index[alias] = entity.id
        for rd in payload.get("relations", []):
            relation = Relation.from_dict(rd)
            model.relations[relation.id] = relation
            if relation.ref_key:
                model._ref_key_index[relation.ref_key] = relation.id
            pair_key = f"{relation.source}->{relation.target}"
            model._pair_occurrence[pair_key] = model._pair_occurrence.get(pair_key, 0) + 1
        return model

    def clear(self) -> None:
        self.entities.clear()
        self.relations.clear()
        self._name_index.clear()
        self._alias_index.clear()
        self._pair_occurrence.clear()
        self._ref_key_index.clear()

    def clone(self) -> "WorldModel":
        """
        深いコピーを返す。World State Engine (Phase 0b) が
        Initial State を破壊せずにEventを再生するために使う (§9)。
        JSON往復による素朴な実装だが、Entity/Relationの構造が
        JSON互換である限り正しく複製できる。
        """
        return WorldModel.from_json(self.to_json())
