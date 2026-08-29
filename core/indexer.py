"""
Axral Codex - Secondary / Background Indexer (Phase 1.5)

plan.md (v2) §4.3, §4.5.1 に対応。

設計原則:
  - Primary Parserとは完全に分離する (§4.3, §19.1/§19.2)。
    このモジュールはPrimary Parserの結果 (natural_lines) を「読むだけ」で、
    Canonical Data (WorldModel) を直接書き換えることは絶対にしない。
  - Candidate ≠ Fact (§4.3.1)。ここで生成するのはあくまでCandidateであり、
    ユーザーが承認するまでConfirmed Relationにはならない。
  - Confidenceは MVP2 の方針どおり Rule-based Signal のみで算出する (§4.5.1)。
    Embedding Signal / LLM Signal は将来の拡張として confidence_breakdown に
    キーだけ予約してあるが、この実装では rule 以外のSignalは常に空。
  - 曖昧性 (§5, §15.6) はErrorにせず "Unresolved Reference" として個別に扱う。

既知の制約 (MVPとして明示的に許容している簡略化):
  - Entity mentionの検出は「既知のEntity名/aliasの部分文字列一致」による素朴な方式。
    日本語には単語境界がないため、真の形態素解析ではない。
  - Relation Keywordの語彙は固定辞書。未知の関係表現は候補化されない
    (Silent Guessをしないという原則 §18.2 を優先し、拾えない方を選ぶ)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Entity
from .parser import NaturalLine

# 関係キーワード辞書: 表層形 -> 正規化された関係タイプ
# (辞書拡充はここに追記するだけで済むよう、他ロジックから分離してある)
RELATION_KEYWORDS: dict[str, str] = {
    "所属していた": "所属",
    "所属する": "所属",
    "所属": "所属",
    "対立していた": "対立",
    "対立する": "対立",
    "対立": "対立",
    "敵対": "対立",
    "尊敬していた": "尊敬",
    "尊敬する": "尊敬",
    "尊敬": "尊敬",
    "師事": "師事",
    "同盟": "同盟",
    "友好": "友好",
    "協力": "協力",
    "裏切った": "裏切り",
    "裏切り": "裏切り",
    "殺した": "殺害",
    "殺害": "殺害",
    "婚姻": "婚姻",
    "結婚": "婚姻",
    "親子": "親子",
    "師弟": "師弟",
    "部下": "上下関係",
    "上司": "上下関係",
    "統治していた": "統治",
    "統治する": "統治",
    "統治": "統治",
}

# 否定表現。近傍に出現した場合はConfidenceを下げる（断定を避ける）。
_NEGATION_PATTERNS = ["ない", "なかった", "ません", "ではない", "ではなかった"]

# 未解決参照とみなす代名詞・指示語（§15.6 Ambiguity, Errorにはしない）
_PRONOUNS = ["彼女", "彼", "それ", "その", "あの", "あいつ", "この者"]

_HIGH = 0.75
_MEDIUM = 0.5


@dataclass
class ConfidenceBreakdown:
    """§4.5.1: confidenceの内訳を保持し、UI上で根拠を説明できるようにする。"""
    rule_signal: float = 0.0
    embedding_signal: float | None = None  # 未実装 (将来拡張の予約枠)
    llm_signal: float | None = None  # 未実装 (将来拡張の予約枠)

    @property
    def total(self) -> float:
        # MVP2ではrule_signalのみを採用する (§4.5.1)。
        return max(0.0, min(1.0, self.rule_signal))

    @property
    def level(self) -> str:
        t = self.total
        if t >= _HIGH:
            return "high"
        if t >= _MEDIUM:
            return "medium"
        return "low"


@dataclass
class Candidate:
    """Confirmされるまで、これはFactではない (§4.3.1)。"""
    id: str
    line: int
    source_text: str
    source_name: str
    target_name: str
    rel_type: str
    breakdown: ConfidenceBreakdown
    ambiguous: bool = False

    @property
    def confidence(self) -> float:
        return self.breakdown.total

    @property
    def confidence_level(self) -> str:
        return self.breakdown.level


@dataclass
class AmbiguityNote:
    """§15.6: 曖昧性そのものはErrorではなくinfo扱い。"""
    line: int
    message: str


@dataclass
class IndexResult:
    candidates: list[Candidate] = field(default_factory=list)
    ambiguities: list[AmbiguityNote] = field(default_factory=list)


def _find_entity_mentions(line: str, entities: list[Entity]) -> list[tuple[int, int, Entity]]:
    """
    既知のEntity名/aliasを、重複しない最長一致でlineから検出する。
    戻り値は (start, end, Entity) のリストで、出現位置順にソート済み。
    """
    raw_matches: list[tuple[int, int, Entity]] = []
    for entity in entities:
        names = [entity.name, *entity.aliases]
        for name in names:
            if not name:
                continue
            for m in re.finditer(re.escape(name), line):
                raw_matches.append((m.start(), m.end(), entity))

    # 長いマッチを優先しつつ、重複範囲を除外する
    raw_matches.sort(key=lambda t: (t[1] - t[0]), reverse=True)
    accepted: list[tuple[int, int, Entity]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, entity in raw_matches:
        if any(not (end <= os or start >= oe) for os, oe in occupied):
            continue
        accepted.append((start, end, entity))
        occupied.append((start, end))

    accepted.sort(key=lambda t: t[0])
    return accepted


def _find_keyword(line: str) -> tuple[str, str, int] | None:
    """行中から関係キーワードを1つ探す。複数マッチする場合は最長一致を優先。"""
    best: tuple[str, str, int] | None = None
    for surface, rel_type in RELATION_KEYWORDS.items():
        idx = line.find(surface)
        if idx == -1:
            continue
        if best is None or len(surface) > len(best[0]):
            best = (surface, rel_type, idx)
    return best


def _has_negation_near(line: str, keyword_idx: int, keyword_len: int) -> bool:
    window = line[keyword_idx : keyword_idx + keyword_len + 6]
    return any(neg in window for neg in _NEGATION_PATTERNS)


def index_natural_lines(
    natural_lines: list[NaturalLine], known_entities: list[Entity]
) -> IndexResult:
    """
    Secondary Indexer本体。Primary Parserが無視した行だけを対象にする。

    known_entitiesはPrimary Parserがすでに確定させたEntity一覧
    (明示宣言・shorthand双方を含む)。Secondary IndexerはこのリストにないEntityを
    勝手に新規生成しない — Entity Candidate Detectionの本格実装は将来のPhaseで、
    ここでは「既存Entityへの言及」だけを候補化する。
    """
    result = IndexResult()
    counter = 0

    for nl in natural_lines:
        line = nl.text

        mentions = _find_entity_mentions(line, known_entities)
        keyword = _find_keyword(line)

        pronoun_hit = any(p in line for p in _PRONOUNS)

        if keyword is None:
            if pronoun_hit:
                # キーワードは無いが代名詞だけがある行は候補化のしようがないため無視
                pass
            continue

        surface, rel_type, kw_idx = keyword
        negated = _has_negation_near(line, kw_idx, len(surface))

        if pronoun_hit and len(mentions) < 2:
            result.ambiguities.append(
                AmbiguityNote(
                    line=nl.line,
                    message=f"未解決参照 (代名詞の指す先が特定できません): 「{line}」",
                )
            )
            continue

        if len(mentions) < 2:
            # Entityが1つ以下しか見つからない場合は候補化しない (Silent Guessをしない, §18.2)
            continue

        distinct_entities: list[Entity] = []
        seen_ids: set[str] = set()
        for _, _, ent in mentions:
            if ent.id not in seen_ids:
                distinct_entities.append(ent)
                seen_ids.add(ent.id)

        if len(distinct_entities) > 2:
            result.ambiguities.append(
                AmbiguityNote(
                    line=nl.line,
                    message=(
                        f"複数のEntityが1文に登場しており、関係の対応が曖昧です "
                        f"({', '.join(e.name for e in distinct_entities)}): 「{line}」"
                    ),
                )
            )
            # 曖昧性は通知しつつ、隣接ペアごとに低confidenceの候補は出しておく
            pairs = list(zip(distinct_entities, distinct_entities[1:]))
            ambiguous = True
        else:
            pairs = [(distinct_entities[0], distinct_entities[1])]
            ambiguous = False

        for source_ent, target_ent in pairs:
            breakdown = ConfidenceBreakdown()
            rule = 0.3  # entity_match: 両Entityが既知
            rule += 0.3  # keyword_match: 関係キーワードが見つかった
            # 語順ボーナス: 日本語は述語(キーワード)が文末寄りに来るのが自然
            if kw_idx > max(m[0] for m in mentions[:2]):
                rule += 0.2
            if negated:
                rule -= 0.35
            if ambiguous:
                rule -= 0.25
            breakdown.rule_signal = rule

            counter += 1
            result.candidates.append(
                Candidate(
                    id=f"cand_{nl.line}_{counter}",
                    line=nl.line,
                    source_text=line,
                    source_name=source_ent.name,
                    target_name=target_ent.name,
                    rel_type=rel_type,
                    breakdown=breakdown,
                    ambiguous=ambiguous,
                )
            )

    return result
