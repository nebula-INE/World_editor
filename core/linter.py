"""
Axral Codex - Worldbuilding Linter (Phase 4, §15)

plan.md (v2) §15 に対応。既存の各Phaseが生成する情報を集約し、
「世界観そのものを検証する」レイヤーとして提供する:

  §15.1 Temporal Contradiction : WorldStateEngine (Phase 0b) のEvent履歴を検査
  §15.3 Relation Contradiction : Relation.valid_from/valid_to の矛盾 (最小版)
  §15.4 Missing Reference      : relation_add Effectが存在しないEntityを参照
  §15.5 Duplicate Entity       : 型が食い違う重複Entity宣言 (Primary Parserで検出)
  §15.6 Ambiguity              : Secondary Indexer (Phase 1.5) のAmbiguityNoteを集約

意図的に簡略化していること:
  §15.2 Membership Contradiction は「参加/離脱」の専用Effectを持たないため
  (現在のUIは entity_existence / relation_status のみをサポート)、
  素朴な形での実装は見送っている。Effect語彙にjoin/leaveが追加され次第、
  ここに実装を追加できるよう設計だけは分離してある。

  §15.3 Relation Contradiction の「論理的に成立しないRelation」の一般的な
  検出にはドメインオントロジー(関係の対義語辞書など)が必要で、plan.md自体も
  詳細を定めていないため、ここでは valid_from/valid_to の数値矛盾という
  スキーマから機械的に判定できる範囲に絞っている。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .indexer import IndexResult
from .models import WorldModel
from .parser import ParseResult
from .world_state import WorldStateEngine

DEAD_VALUES = {"dead", "deceased", "destroyed", "died"}


class Severity(str, Enum):
    WARNING = "warning"
    INFO = "info"


@dataclass
class LintIssue:
    code: str
    severity: Severity
    message: str
    line: int | None = None


def lint(
    parse_result: ParseResult,
    engine: WorldStateEngine,
    index_result: IndexResult | None = None,
) -> list[LintIssue]:
    """
    既存の各Phaseの検査結果 + 新規のWorld State検査をまとめて1つのリストにする。
    UI側 (ui/linter_panel.py) はこのリストを表示するだけで良い。
    """
    issues: list[LintIssue] = []
    issues.extend(_parser_issues(parse_result))
    issues.extend(_patch_conflicts(parse_result))
    if index_result is not None:
        issues.extend(_ambiguities(index_result))
    issues.extend(_temporal_contradictions(engine))
    issues.extend(_relation_date_inconsistencies(parse_result.model))
    issues.extend(_missing_references_over_time(engine))
    return issues


def _parser_issues(parse_result: ParseResult) -> list[LintIssue]:
    """
    Primary Parserが検出したissue全般 (§15.5 Duplicate Entityの重複型宣言、
    Patch対象が見つからない場合など) をそのまま集約する。
    """
    return [
        LintIssue(code="PARSE", severity=Severity.WARNING, message=i.message, line=i.line)
        for i in parse_result.issues
    ]


def _patch_conflicts(parse_result: ParseResult) -> list[LintIssue]:
    out = []
    for c in parse_result.patch_conflicts:
        out.append(
            LintIssue(
                code="PATCH_CONFLICT",
                severity=Severity.WARNING,
                message=(
                    f"「{c.ref_key}」の {c.field} でConflict: "
                    f'Original="{c.text_value}" / Patch="{c.patch_value}" '
                    f'(Patch作成時のOriginal想定値="{c.expected_was}")'
                ),
                line=c.line,
            )
        )
    return out


def _ambiguities(index_result: IndexResult) -> list[LintIssue]:
    """§15.6: 曖昧性そのものはErrorではなくInfo扱い。"""
    return [
        LintIssue(code="AMBIGUITY", severity=Severity.INFO, message=a.message, line=a.line)
        for a in index_result.ambiguities
    ]


def _temporal_contradictions(engine: WorldStateEngine) -> list[LintIssue]:
    """
    §15.1: Entityが死亡 (existenceがDEAD_VALUESへ変化) した後のtimestampで、
    そのEntityが参加する別のEventが存在する場合、矛盾として報告する。
    復活 (existenceが非DEAD_VALUESへ戻る) があれば、その時点で死亡区間を閉じる。
    """
    issues: list[LintIssue] = []
    events = engine.events_sorted()

    death_periods: dict[str, list[list]] = {}
    for event in events:
        for effect in event.effects:
            if effect.kind != "entity_existence":
                continue
            entity_id = effect.target_id
            existence = str(effect.payload.get("existence", "")).lower()
            periods = death_periods.setdefault(entity_id, [])
            if existence in DEAD_VALUES:
                periods.append([event.timestamp, None])
            else:
                for period in reversed(periods):
                    if period[1] is None and period[0] < event.timestamp:
                        period[1] = event.timestamp
                        break

    for event in events:
        for participant_id in event.participants:
            for ts, end in death_periods.get(participant_id, []):
                if not (ts < event.timestamp and (end is None or event.timestamp < end)):
                    continue
                is_self_existence_change = any(
                    eff.kind == "entity_existence" and eff.target_id == participant_id
                    for eff in event.effects
                )
                if is_self_existence_change:
                    continue
                state = engine.state_at(ts)
                entity = state.entities.get(participant_id)
                name = entity.name if entity else participant_id
                issues.append(
                    LintIssue(
                        code="TEMPORAL_CONTRADICTION",
                        severity=Severity.WARNING,
                        message=(
                            f"{name} は t={ts} で死亡状態になっていますが、"
                            f't=%d の Event「%s」に関与しています。'
                            % (event.timestamp, event.type)
                        ),
                    )
                )
    return issues


def _relation_date_inconsistencies(model: WorldModel) -> list[LintIssue]:
    """§15.3 Relation Contradictionの最小版: valid_from/valid_toが数値として矛盾する場合。"""
    issues: list[LintIssue] = []
    for relation in model.relations.values():
        if relation.valid_from is None or relation.valid_to is None:
            continue
        try:
            vf = int(relation.valid_from)
            vt = int(relation.valid_to)
        except (TypeError, ValueError):
            continue
        if vt < vf:
            issues.append(
                LintIssue(
                    code="RELATION_DATE_CONTRADICTION",
                    severity=Severity.WARNING,
                    message=(
                        f"「{relation.ref_key or relation.id}」は valid_to ({vt}) が "
                        f"valid_from ({vf}) より前になっています。"
                    ),
                )
            )
    return issues


def _missing_references_over_time(engine: WorldStateEngine) -> list[LintIssue]:
    """§15.4: relation_add Effectが、その時点で存在しないEntityを参照している場合。"""
    issues: list[LintIssue] = []
    for event in engine.events_sorted():
        for effect in event.effects:
            if effect.kind != "relation_add":
                continue
            state = engine.state_at(event.timestamp)
            for key in ("source", "target"):
                entity_id = effect.payload.get(key)
                if entity_id and entity_id not in state.entities:
                    issues.append(
                        LintIssue(
                            code="MISSING_REFERENCE",
                            severity=Severity.WARNING,
                            message=(
                                f"t={event.timestamp} の relation_add Effectが "
                                f"存在しないEntity ({entity_id}) を参照しています。"
                            ),
                        )
                    )
    return issues
