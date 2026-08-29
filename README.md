# Axral Codex — MVP1 (Explicit Text → Graph)

`plan.md` (v2) の MVP1「Explicit Text → Graph」を実装したものです。
AI/NLPには依存せず、明示的な Codex Syntax のみを解釈します（§4.2, §18.3）。

## 対応スコープ

| plan.md | 実装状況 |
|---|---|
| Phase 0a: Entity/Relation 最小Schema | `core/models.py` |
| Phase 1: 決定論的Primary Parser | `core/parser.py` |
| Phase 1: Live Preview (§4.6) | `main.py`（デバウンス付きtextChanged） |
| Phase 1.5: Secondary Indexer（自然言語→Candidate, Rule-basedのみ, §4.5.1） | `core/indexer.py` |
| Phase 1.5: Inline Suggestions / User Confirmation (§4.3.1) | `ui/candidate_panel.py` |
| Phase 2: Graph Canvas（読み取り専用の最小版） | `ui/graph_view.py` |
| Relation Status (§7.1) の線種表現 | 実装済み（confirmed=実線 / hypothetical=破線 / rumor=点線） |
| Reality vs Knowledge 拡張点 (§7.2.1) | `Relation.perspective` フィールドとして予約済み（未使用） |
| Schema Versioning (§18.8) | `schema_version` フィールドとして予約済み |

**スコープ外**（今後のPhaseで追加）:
- Confidence算出へのEmbedding Signal / LLM Signalの追加（§4.5.1、Phase 1.5後半）
- Canvas編集・Non-destructive Text Sync本編・Patch/Conflict UI（Phase 2本編）
- Timeline / Layer / World State / Snapshot（Phase 3, MVP4）
- Worldbuilding Linter（Phase 4）

## Secondary Indexer（自然言語からのCandidate抽出）の仕組み

- 既知のEntity名/aliasの部分文字列一致で「Entity mention」を検出（形態素解析なし、素朴な方式）。
- 固定辞書（`RELATION_KEYWORDS`）にある関係キーワードが1文に見つかり、既知Entityの言及が
  ちょうど2つある場合にCandidateを1件生成する。
- Confidenceは Rule-based Signal のみで算出（§4.5.1でMVP2として定めた方針どおり）:
  entity一致 + keyword一致 + 語順ボーナス − 否定表現ペナルティ − 曖昧性ペナルティ。
- 3つ以上のEntityが1文に登場する場合は「曖昧」として通知しつつ、隣接ペアごとに
  低confidenceの候補を出す。代名詞（彼/それ等）で先行詞が特定できない場合は
  Candidateを生成せず、Unresolved Referenceとして通知するのみ（§15.6に準拠、Errorにはしない）。
- Accept を押すと、Canonical Dataを直接書き換えるのではなく、本文末尾の
  `# Generated Relations` セクションへ確定Codex Syntax行（例: `A -> B : 所属`）を
  追記し、それをPrimary Parserに再解釈させる（§10.1 Generated Sectionの考え方を流用。
  本格的なPatchシステムはPhase 2で実装）。
- Ignore を押した候補は、セッション中は同じ行・同じ候補内容であれば再表示されない
  （テキストにもCanonical Dataにも一切影響しない）。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate  # Windowsは .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 使い方

左側のエディタに Codex Syntax を書くと、右側のグラフが自動更新されます。

```text
[A:Character]
[B:Organization]

[A:Character] -> [B:Organization] : 所属
A -> B : 対立
```

- `[名前:型]` … Entity宣言
- `[A:型] -> [B:型] : 関係名` … 型指定付きの明示的Relation
- `A -> B : 関係名` … 型指定なしのshorthand（既出のEntity名を参照。型は自動的に "Unknown" になり、後から `[A:型]` の宣言があれば確定します）

File メニューから:
- Codex Syntaxテキストの読み込み/保存
- Canonical Data (Entity/Relation) のJSONエクスポート

## ディレクトリ構成

```
axral_codex/
├── main.py              # アプリ本体 (Editor + Live Graph Preview)
├── core/
│   ├── models.py         # Canonical Data Model (Entity, Relation, WorldModel)
│   └── parser.py         # Primary Parser (Codex Syntax)
└── ui/
    └── graph_view.py      # Graph Canvasの最小描画 (QGraphicsScene)
```

## 次にやると良いこと（Phase 2以降）

1. `ui/graph_view.py` にノードのドラッグ移動とCanvas→Text Patch書き出しを追加し、
   Phase 2 (Non-destructive Text Sync本編・Patch/Conflict UI) へ接続する。
2. `core/models.py` に Event / WorldState / Snapshot を追加し（Phase 0b, §9）、
   Timeline Lens (Phase 3) の土台にする。
3. `core/indexer.py` のConfidence算出にEmbedding Signalを追加し（§4.5.1後半）、
   `confidence_breakdown`のembedding_signalフィールドを実際に埋める。
