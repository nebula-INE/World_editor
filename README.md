# Axral Codex — MVP1 (Explicit Text → Graph)

`plan.md` (v2) の MVP1「Explicit Text → Graph」を実装したものです。
AI/NLPには依存せず、明示的な Codex Syntax のみを解釈します（§4.2, §18.3）。

## 対応スコープ

| plan.md | 実装状況 |
|---|---|
| Phase 0a: Entity/Relation 最小Schema | `core/models.py` |
| Phase 1: 決定論的Primary Parser | `core/parser.py` |
| Phase 1: Live Preview (§4.6) | `main.py`（デバウンス付きtextChanged） |
| Phase 2: Graph Canvas（読み取り専用の最小版） | `ui/graph_view.py` |
| Relation Status (§7.1) の線種表現 | 実装済み（confirmed=実線 / hypothetical=破線 / rumor=点線） |
| Reality vs Knowledge 拡張点 (§7.2.1) | `Relation.perspective` フィールドとして予約済み（未使用） |
| Schema Versioning (§18.8) | `schema_version` フィールドとして予約済み |

**スコープ外**（今後のPhaseで追加）:
- Secondary / Background Indexer（自然言語からのCandidate抽出, Phase 1.5）
- Canvas編集・Non-destructive Text Sync・Patch/Conflict UI（Phase 2本編）
- Timeline / Layer / World State / Snapshot（Phase 3, MVP4）
- Worldbuilding Linter（Phase 4）

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

## 次にやると良いこと（Phase 1.5以降）

1. `core/indexer.py` を新設し、Secondary Indexer（自然言語→Candidate抽出）を
   Primary Parserと完全に分離した形で追加する（§4.3）。まずRule-based Confidence
   のみ（§4.5.1）。
2. `ui/graph_view.py` にノードのドラッグ移動とCanvas→Text Patch書き出しを追加し、
   Phase 2 (Non-destructive Text Sync) へ接続する。
3. `core/models.py` に Event / WorldState / Snapshot を追加し（Phase 0b, §9）、
   Timeline Lens (Phase 3) の土台にする。
