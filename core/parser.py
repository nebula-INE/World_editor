"""
Axral Codex - Primary Parser (Phase 1: Deterministic Codex Parser)

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

Incremental Parsing (§12.1) は将来の最適化事項であり、MVP1では
全文を毎回再解析する素朴な実装とする。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import SourceRef, WorldModel

# [名前:型]
_ENTITY_DECL_RE = re.compile(r"^\[(?P<name>[^\]:]+):(?P<type>[^\]]+)\]$")

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
class ParseResult:
    model: WorldModel
    issues: list[ParseIssue]
    natural_lines: list[NaturalLine]


def parse_codex_syntax(text: str) -> ParseResult:
    """
    Codex Syntaxのみを解釈し、Canonical Data (WorldModel) を構築する。

    自然言語の地の文 (例: "AはBの組織に所属していた。") は対象外であり、
    構文にマッチしない行は単に無視する (Errorにはしない。Phase 1.5で
    Secondary Indexerが同じ行からcandidateを抽出する設計)。
    """
    model = WorldModel()
    issues: list[ParseIssue] = []
    natural_lines: list[NaturalLine] = []

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        # コードフェンスや見出しなど、明らかにCodex Syntaxでない行は早期スキップ
        # (Secondary Indexerの対象にもしない — 見出し/コードブロックは地の文ではない)
        if line.startswith("#") or line.startswith("```"):
            continue

        ref = SourceRef(line=lineno, text=line)

        m = _ENTITY_DECL_RE.match(line)
        if m:
            model.get_or_create_entity(
                name=m.group("name").strip(),
                type_=m.group("type").strip(),
                source_ref=ref,
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

    return ParseResult(model=model, issues=issues, natural_lines=natural_lines)
