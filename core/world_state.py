"""
Axral Codex - World State Engine (Phase 0b, §9)

plan.md (v2) §9, §9.1, §9.1.1, §9.1.2, §9.1.3 に対応。

```
Initial State
     +
   Events
     ↓
World State
```

設計:
  - Initial State は WorldModel (Primary Parserが解釈したCanonical Data) の
    スナップショットで、"Event適用前の基準状態" として扱う。
  - Eventは時系列順に適用され、都度 entities/relations のコピーを変更していく。
  - Snapshotting Strategy (§9.1): 一定間隔 または Snapshot Trigger (Tear/Chapter/
    MajorEvent/User-defined) ごとにWorldStateをキャッシュし、
    Timeline Query (§9.1.2) を高速化する。
  - Snapshot Invalidation (§9.1.3): 過去のEventが追加/変更/削除された場合、
    その時点以降のSnapshotキャッシュを破棄し、次回アクセス時に遅延再構築する。

このモジュールはUIに依存しない。Timeline Lens (Phase 3) はこのクラスの
`state_at()` を呼ぶだけで良い設計にしてある。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .events import Event
from .models import Entity, Relation, WorldModel

SNAPSHOT_INTERVAL = 20  # 一定数のEvent経過後にSnapshotを取る (§9.1.1)


@dataclass
class WorldState:
    """特定時点のWorld State。entities/relationsはその時点でのスナップショット。"""
    timestamp: int
    entities: dict[str, Entity] = field(default_factory=dict)
    relations: dict[str, Relation] = field(default_factory=dict)

    def clone(self) -> "WorldState":
        model = WorldModel()
        model.entities = self.entities
        model.relations = self.relations
        cloned = model.clone()
        return WorldState(
            timestamp=self.timestamp,
            entities=cloned.entities,
            relations=cloned.relations,
        )


class WorldStateEngine:
    """
    Initial State (WorldModel) + Event履歴から、任意時点のWorld Stateを
    再構築するエンジン。Snapshotによって毎回全Eventを再生しないようにする。
    """

    def __init__(self, initial_model: WorldModel) -> None:
        self._initial = initial_model.clone()
        self._events: dict[str, Event] = {}
        # timestamp -> WorldState のキャッシュ。
        # 「そのtimestampの直後まで適用済みの状態」を意味する。
        self._snapshots: dict[int, WorldState] = {}
        self._sorted_cache: list[Event] | None = None

    # ---- Initial State management -----------------------------------------

    def set_initial_model(self, model: WorldModel) -> None:
        """
        Primary Parserの再解析結果でInitial Stateを更新する。
        Human-authored Text側の変更はここを通じてWorld State Engineに反映される。
        既存のEventはそのまま保持しつつ、全Snapshotを無効化して整合性を保つ。
        """
        self._initial = model.clone()
        self._snapshots.clear()

    # ---- Event management (add/remove -> Invalidation §9.1.3) --------------

    def add_event(self, event: Event) -> None:
        self._events[event.id] = event
        self._invalidate_from(event.timestamp)
        self._sorted_cache = None

    def remove_event(self, event_id: str) -> None:
        event = self._events.pop(event_id, None)
        self._sorted_cache = None
        if event is not None:
            self._invalidate_from(event.timestamp)

    def update_event(self, event: Event) -> None:
        """既存Eventの内容変更 (§9.1.3 'Event 100 changed' に相当)。"""
        old = self._events.get(event.id)
        self._events[event.id] = event
        self._sorted_cache = None
        invalidate_ts = min(old.timestamp, event.timestamp) if old else event.timestamp
        self._invalidate_from(invalidate_ts)

    def events_sorted(self) -> list[Event]:
        if self._sorted_cache is None:
            self._sorted_cache = sorted(self._events.values(), key=lambda e: (e.timestamp, e.id))
        return self._sorted_cache

    # ---- Snapshot Invalidation (§9.1.3) -------------------------------------

    def _invalidate_from(self, timestamp: int) -> None:
        """
        timestamp以降のSnapshotを無効化する。
        次回 state_at() が呼ばれた際、それより前の有効なSnapshot (または
        Initial State) から遅延再構築される。
        """
        for ts in [t for t in self._snapshots if t >= timestamp]:
            del self._snapshots[ts]

    # ---- Timeline Query (§9.1.2) ---------------------------------------------

    def state_at(self, timestamp: int) -> WorldState:
        """
        Nearest Snapshot -> Replay remaining Events -> Target World State
        という§9.1.2のフローそのままの実装。
        """
        base_ts, base_state = self._nearest_snapshot_at_or_before(timestamp)

        events = [e for e in self.events_sorted() if base_ts < e.timestamp <= timestamp]

        state = base_state.clone()
        for event in events:
            self._apply_event(state, event)
            state.timestamp = event.timestamp
            if event.triggers_snapshot:
                # Snapshot候補地点なのでキャッシュしておく (§9.1.1)
                self._snapshots[event.timestamp] = state.clone()

        # 一定数のEvent経過後にもSnapshotを取る (§9.1.1)
        if len(events) >= SNAPSHOT_INTERVAL:
            self._snapshots[timestamp] = state.clone()

        state.timestamp = timestamp
        return state

    def _nearest_snapshot_at_or_before(self, timestamp: int) -> tuple[int, WorldState]:
        candidates = [ts for ts in self._snapshots if ts <= timestamp]
        if not candidates:
            initial_state = WorldState(
                timestamp=float("-inf"),
                entities=self._initial.entities,
                relations=self._initial.relations,
            )
            return float("-inf"), initial_state
        nearest = max(candidates)
        return nearest, self._snapshots[nearest]

    # ---- Effect application --------------------------------------------------

    @staticmethod
    def _apply_event(state: WorldState, event: Event) -> None:
        for effect in event.effects:
            WorldStateEngine._apply_effect(state, effect)

    @staticmethod
    def _apply_effect(state: WorldState, effect) -> None:
        if effect.kind == "relation_add":
            payload = effect.payload
            rel_id = effect.target_id or f"rel_{len(state.relations)}_{payload.get('type', '')}"
            state.relations[rel_id] = Relation(
                id=rel_id,
                source=payload["source"],
                target=payload["target"],
                type=payload.get("type", "関連"),
                status=payload.get("status", "confirmed"),
            )
        elif effect.kind == "relation_status":
            relation = state.relations.get(effect.target_id)
            if relation is not None:
                relation.status = effect.payload.get("status", relation.status)
        elif effect.kind == "relation_end":
            relation = state.relations.get(effect.target_id)
            if relation is not None:
                relation.valid_to = effect.payload.get("valid_to")
        elif effect.kind == "entity_attribute":
            entity = state.entities.get(effect.target_id)
            if entity is not None:
                key = effect.payload.get("key")
                if key:
                    entity.attributes[key] = effect.payload.get("value")
        elif effect.kind == "entity_existence":
            entity = state.entities.get(effect.target_id)
            if entity is not None:
                entity.existence = effect.payload.get("existence", entity.existence)
        # 未知のkindは無視する (Silent Guessをしない。将来Linterで警告対象にできる)
