"""
Axral Codex - Primary Parser (Phase 1 / Phase 2: Deterministic Codex Parser + Patch)

plan.md (v2) §4.2 の対象:
  明示的に記述された構造 (Entity Declaration / Explicit Relation) だけを扱う。
  Primary Parserは「賢く推測すること」をしない — 曖昧な行は無視する
  (§18.2 Never Guess Silently)。自然言語解析 (Secondary Indexer) は
  このモジュールの責務ではなく、Phase 1.5で別モジュールとして追加する。

対応する構文 (plan.md §2.2, §6, §7 に準拠):
  1. Entity宣言:         [名前:型]
  2. 明示的Relation:      [A:型] -> [B:型] : 関係
  3. Shorthand Relation:  A -> B : 関係
     (既出のEntity名を参照する。未出の場合は type="Unknown" で自動生成し、
      後から明示宣言があれば型を確定させる — models.get_or_create_entity 参照)
  4. Patch (Phase 2, §10.2):
        PATCH SourceName->TargetName#0:
          type = "協力"  # was: "対立"
     Canvasからの変更をOriginal Textに直接書き込まず、Patchとして層を分ける
     ための構文。"# was: ..." は、Patch作成時点でのOriginal側の値を記録しておく
     ためのもので、Conflict検出 (§11) に使う。

Incremental Parsing (§12.1) は将来の最適化事項であり、MVP1では
全文を毎回再解析する素朴な実装とする。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import LAYER_HIERARCHY, Relation, SourceRef, WorldModel, is_valid_layer

# [名前:型] または [名前:型:Layer]
_ENTITY_DECL_RE = re.compile(
    r"^\[(?P<name>[^\]:]+):(?P<type>[^\]:]+)(?::(?P<layer>[^\]]+))?\]$"
)

# [A:型] -> [B:型] : 関係   （関係名は省略可）
_EXPLICIT_RELATION_RE = re.compile(
    r"^\[(?P<sname>[^\]:]+):(?P<stype>[^\]]+)\]\s*->\s*"
    r"\[(?P<tname>[^\]:]+):(?P<ttype>[^\]]+)\]"
    r"(?:\s*:\s*(?P<rtype>.+))?$"
)

# A -> B : 関係  （型指定なしのshorthand。関係名は必須）
_SHORTHAND_RELATION_RE = re.compile(
    r"^(?P<sname>[^\[\]:>]+?)\s*->\s*(?P<tname>[^\[\]:>]+?)\s*:\s*(?P<rtype>.+)$"
)

# PATCH SourceName->TargetName#0:
_PATCH_HEADING_RE = re.compile(r"^PATCH\s+(?P<ref>.+?)\s*:$")

# key = "value"  [# was: "was_value"]
_PATCH_FIELD_RE = re.compile(
    r'^(?P<key>[A-Za-z_]+)\s*=\s*"(?P<value>[^"]*)"'
    r'(?:\s*#\s*was:\s*"(?P<was>[^"]*)")?\s*$'
)


@dataclass
class ParseIssue:
    line: int
    message: str


@dataclass
class NaturalLine:
    """Primary Parserがどの構文にもマッチせず無視した行。Secondary Indexerの入力になる。"""
    line: int
    text: str


@dataclass
class PatchConflict:
    """
    §11 Conflict Resolution: PatchのField値がOriginal Textとかみ合わない状態。
    §18.4 Human-authored Data Wins の原則により、Conflict中はPatchを自動適用せず、
    Original Textの値を維持したままユーザーの選択を待つ。
    """
    ref_key: str
    field: str
    line: int
    text_value: str  # Original Text側の現在値
    patch_value: str  # Patchが適用しようとしている値
    expected_was: str  # Patch作成時点でOriginal側にあったはずの値


@dataclass
class ParseResult:
    model: WorldModel
    issues: list[ParseIssue]
    natural_lines: list[NaturalLine]
    patch_conflicts: list[PatchConflict] = field(default_factory=list)


def extract_relation_type(line: str) -> str | None:
    """
    Explicit RelationまたはShorthand Relationの行から、関係タイプだけを取り出す。

    Canvas編集 (Phase 2, main.py) が「Patch適用後の表示値」ではなく
    「Original Textに実際に書かれている現在値」を求めるためのユーティリティ。
    Relation.typeフィールドはPatch適用時に直接書き換わるため、
    source_refs[0].text (常にその時点のOriginal Textを反映する) から
    再度この関数で抽出することで、Patch適用の影響を受けない値が得られる。
    """
    line = line.strip()
    m = _EXPLICIT_RELATION_RE.match(line)
    if m:
        return (m.group("rtype") or "").strip() or "関連"
    m = _SHORTHAND_RELATION_RE.match(line)
    if m:
        return m.group("rtype").strip()
    return None


def parse_codex_syntax(text: str) -> ParseResult:
    """
    Codex Syntaxのみを解釈し、Canonical Data (WorldModel) を構築する。

    自然言語の地の文 (例: "AはBの組織に所属していた。") は対象外であり、
    構文にマッチしない行は単に無視する (Errorにはしない。Phase 1.5で
    Secondary Indexerが同じ行からcandidateを抽出する設計)。

    PATCHブロック (Phase 2, §10.2) はEntity/Relation本体の解析が完了した後、
    2段階目として適用する (Patchは既存Relationへの上書きなので、対象が
    先に存在している必要があるため)。
    """
    model = WorldModel()
    issues: list[ParseIssue] = []
    natural_lines: list[NaturalLine] = []
    # ref_key -> {field: (value, was)} の一時バッファ
    pending_patches: dict[str, dict[str, tuple[str, str | None]]] = {}
    pending_patch_lines: dict[str, int] = {}

    in_patch_block = False
    current_patch_ref: str | None = None

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if in_patch_block:
            if line:
                fm = _PATCH_FIELD_RE.match(line)
                if fm:
                    pending_patches.setdefault(current_patch_ref, {})[fm.group("key")] = (
                        fm.group("value"),
                        fm.group("was"),
                    )
                    continue
            # 空行、または key = "value" 以外の行が来たらPatchブロック終了。
            # このあとこの行自体は通常どおり処理する (fallthrough)。
            in_patch_block = False
            current_patch_ref = None

        if not line:
            continue
        # コードフェンスや見出しなど、明らかにCodex Syntaxでない行は早期スキップ
        # (Secondary Indexerの対象にもしない — 見出し/コードブロックは地の文ではない)
        if line.startswith("#") or line.startswith("```"):
            continue

        pm = _PATCH_HEADING_RE.match(line)
        if pm:
            in_patch_block = True
            current_patch_ref = pm.group("ref").strip()
            pending_patch_lines[current_patch_ref] = lineno
            continue

        ref = SourceRef(line=lineno, text=line)

        m = _ENTITY_DECL_RE.match(line)
        if m:
            layer = (m.group("layer") or "").strip() or None
            entity = model.get_or_create_entity(
                name=m.group("name").strip(),
                type_=m.group("type").strip(),
                source_ref=ref,
            )
            if layer:
                if is_valid_layer(layer):
                    if not entity.layer:
                        entity.layer = layer
                else:
                    issues.append(
                        ParseIssue(
                            line=lineno,
                            message=f"未知のLayer '{layer}' (有効値: {', '.join(LAYER_HIERARCHY)})",
                        )
                    )
            continue

        m = _EXPLICIT_RELATION_RE.match(line)
        if m:
            source = model.get_or_create_entity(
                name=m.group("sname").strip(),
                type_=m.group("stype").strip(),
                source_ref=ref,
            )
            target = model.get_or_create_entity(
                name=m.group("tname").strip(),
                type_=m.group("ttype").strip(),
                source_ref=ref,
            )
            rtype = (m.group("rtype") or "").strip() or "関連"
            model.add_relation(source.id, target.id, rtype, ref)
            continue

        m = _SHORTHAND_RELATION_RE.match(line)
        if m:
            source = model.get_or_create_entity(
                name=m.group("sname").strip(), type_=None, source_ref=ref
            )
            target = model.get_or_create_entity(
                name=m.group("tname").strip(), type_=None, source_ref=ref
            )
            rtype = m.group("rtype").strip()
            model.add_relation(source.id, target.id, rtype, ref)
            continue

        # どの構文にもマッチしない行は無視する。
        # (自然言語の地の文として扱われる。Phase 1.5のSecondary Indexerに渡す)
        natural_lines.append(NaturalLine(line=lineno, text=line))

    patch_conflicts = _apply_patches(model, pending_patches, pending_patch_lines, issues)

    return ParseResult(
        model=model,
        issues=issues,
        natural_lines=natural_lines,
        patch_conflicts=patch_conflicts,
    )


def _apply_patches(
    model: WorldModel,
    pending_patches: dict[str, dict[str, tuple[str, str | None]]],
    pending_patch_lines: dict[str, int],
    issues: list[ParseIssue],
) -> list[PatchConflict]:
    """
    §11.1 Source Priority: Human-authored Explicit Text > Generated Patch。
    OriginalのRelation値が、Patch作成時点で記録された"was"値と食い違う場合、
    それは「人間が本文を独自に編集した」ことを意味するのでConflictとし、
    Patchを自動適用しない (Original側の値を維持する)。
    """
    conflicts: list[PatchConflict] = []

    for ref_key, fields in pending_patches.items():
        relation = model.find_by_ref_key(ref_key)
        line_no = pending_patch_lines.get(ref_key, 0)

        if relation is None:
            issues.append(
                ParseIssue(
                    line=line_no,
                    message=f"Patch対象のRelationが見つかりません (ref={ref_key})",
                )
            )
            continue

        for key, (value, was) in fields.items():
            if key == "type":
                current = relation.type
            elif key == "status":
                current = relation.status
            else:
                issues.append(
                    ParseIssue(line=line_no, message=f"未対応のPatchフィールド: {key}")
                )
                continue

            if was is not None and was != current:
                conflicts.append(
                    PatchConflict(
                        ref_key=ref_key,
                        field=key,
                        line=line_no,
                        text_value=current,
                        patch_value=value,
                        expected_was=was,
                    )
                )
                continue  # §18.4: Conflict中はOriginal側の値を維持する

            if key == "type":
                relation.type = value
            elif key == "status":
                relation.status = value

    return conflicts
