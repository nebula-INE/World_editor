# Axral Codex — MVP1 (Explicit Text → Graph)

`plan.md` (v2) の MVP1「Explicit Text → Graph」を実装したものです。
AI/NLPには依存せず、明示的な Codex Syntax のみを解釈します（§4.2, §18.3）。

## 対応スコープ

| plan.md | 実装状況 |
|---|---|
| Phase 0a: Entity/Relation 最小Schema | `core/models.py` |
| Phase 0b: Event Schema | `core/events.py` |
| Phase 0b: World State (Initial + Events, Snapshotting, Invalidation, §9) | `core/world_state.py` |
| Phase 0b: Reference System (Alias解決) | `WorldModel.resolve()` / `add_alias()` (`core/models.py`) |
| Phase 0b: Layer System 階層定義 (§13) | `LAYER_HIERARCHY` (`core/models.py`。Layer SliderなどUI操作はPhase 3) |
| Phase 1: 決定論的Primary Parser | `core/parser.py` |
| Phase 1: Live Preview (§4.6) | `main.py`（デバウンス付きtextChanged） |
| Phase 1.5: Secondary Indexer（自然言語→Candidate, Rule-basedのみ, §4.5.1） | `core/indexer.py` |
| Phase 1.5: Inline Suggestions / User Confirmation (§4.3.1) | `ui/candidate_panel.py` |
| Phase 2: Graph Canvas（ノードのドラッグ移動） | `ui/graph_view.py` |
| Phase 2: Non-destructive Text Sync（Generated Section + PATCH, §10） | `core/parser.py`（PATCH解釈）/ `main.py`（PATCH書き込み） |
| Phase 2: Conflict検出・Resolution UI（§11、Keep Text/Apply Canvas Change/**Merge**/Open Diffの4択） | `core/parser.py`（PatchConflict検出）/ `main.py`（Resolve Conflicts...） |
| Phase 3: Timelineスクラバー（WorldStateEngineを操作するUI, §14） | `ui/timeline_panel.py` |
| Phase 3: Layer Slider（§13） | `ui/timeline_panel.py`（フィルタUI）/ `ui/graph_view.py`（`visible_layers`） |
| Phase 3: Entity宣言へのLayer指定構文 `[名前:型:Layer]` | `core/parser.py` |
| Phase 3: Event追加/削除UI（Add Event Dialog） | `ui/timeline_panel.py` / `main.py` |
| Phase 3: Before/After View（最小版・Change Summaryテキスト） | `main.py`（`_compute_change_summary`） |
| Phase 4: Worldbuilding Linter — Temporal Contradiction (§15.1) | `core/linter.py`（`_temporal_contradictions`） |
| Phase 4: Relation Date Contradiction（§15.3の最小版） | `core/linter.py`（`_relation_date_inconsistencies`） |
| Phase 4: Missing Reference（§15.4） | `core/linter.py`（`_missing_references_over_time`） |
| Phase 4: Duplicate Entity（§15.5、型不一致の重複宣言） | `core/parser.py`（Entity宣言時に検出） |
| Phase 4: Ambiguity（§15.6）の集約表示 | `core/linter.py`（Secondary Indexerの結果を統合） |
| Phase 4: Linter結果パネル | `ui/linter_panel.py` |
| Relation Status (§7.1) の線種表現 | 実装済み（confirmed=実線 / hypothetical=破線 / rumor=点線） |
| Reality vs Knowledge 拡張点 (§7.2.1) | `Relation.perspective` フィールドとして予約済み（未使用） |
| Schema Versioning (§18.8) | `schema_version` フィールドとして予約済み |

**スコープ外**（今後のPhaseで追加）:
- Confidence算出へのEmbedding Signal / LLM Signalの追加（§4.5.1、Phase 1.5後半）
- Infinite Canvas最適化・Undo/Redo（Phase 2の残り・Phase 5）
- ノードを2枚並べるフル版のBefore/After View（現状はテキストによる変化サマリのみ）
- Membership Contradiction（§15.2）: join/leave専用のEffectが未実装のため見送り（詳細は後述）
- 一般的なRelation Contradiction（§15.3）: 関係の対義語辞書などドメインオントロジーが
  必要な部分は未実装。現状はvalid_from/valid_toの数値矛盾のみ検出

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

## World State Engine（Phase 0b）の仕組み

- `WorldModel`（Primary Parserの解析結果）を Initial State とし、
  そこに `Event` を時系列順に適用して任意時点の `WorldState` を再構築する（§9）。
- 1つの `Event` は複数の `Effect` を持てる。対応するEffect kind:
  `relation_add` / `relation_status` / `relation_end` / `entity_attribute` / `entity_existence`。
  Timeline Lens (§14) が変化対象として挙げる所属・生死・Relation・Ownership等は
  これらの組み合わせで表現する。
- Snapshotting Strategy (§9.1): `Event.type` が `Tear` / `Chapter` / `MajorEvent` の場合、
  または `is_snapshot_point=True` の場合、その時点のWorld StateをSnapshotとしてキャッシュする。
  一定数（`SNAPSHOT_INTERVAL`）のEvent経過後にも自動でSnapshotを取る。
- Snapshot Invalidation (§9.1.3): 既存Eventを`update_event()`で変更、または
  `add_event()`/`remove_event()`した場合、その時点以降のSnapshotキャッシュを破棄する。
  次回の `state_at()` 呼び出し時に、有効な最も近いSnapshot（無ければInitial State）
  から遅延再構築される。
- Initial State (`WorldModel`) 自体は `clone()` により複製されてから使われるため、
  Event再生によって元のCanonical Data（Primary Parserの結果）が書き換わることはない。

現時点ではこのEngineを操作するUI（Timelineスクラバー等）は未実装。
Phase 3でLayer Slider・Before/After Viewと合わせて接続する想定。

## Canvas編集 → Patch → Conflict（Phase 2）の仕組み

- Entity/RelationのIDはPhase 2からランダムUUIDではなく**決定論的なID**に変更した
  (Entity: 名前のハッシュ / Relation: `ref_key` = `"SourceName->TargetName#n"`、
  nはそのペアの中での出現順)。MVP1では全文を毎回再解析するため、ランダムIDだと
  再解析のたびにIDが変わってしまいCanvas由来のPatchが対象を見失う問題があった。
- Graph Canvas上でRelationラベルをダブルクリックすると入力ダイアログが開き、
  新しい関係タイプを入力できる。この時点ではCanonical Data・テキストのどちらも
  書き換えず、`relation_type_edit_requested(ref_key, old_type, new_type)` シグナルを
  発行するのみ（Canvasは提案するだけ、という§10.1の原則）。
- `main.py`側がこれを受けて、本文の `# Generated Relations` セクションに
  ```
  PATCH A->B#0:
    type = "協力"  # was: "対立"
  ```
  という形式でPatchを書き込む。`# was: "..."` はPatch作成時点のOriginal Text側の
  値を記録したもので、Conflict検出に使う。同じ`ref_key`を再編集した場合は
  新しいPatchブロックを追加するのではなく、既存ブロックを更新する。
- Primary Parserは２パス構成になっている: 1パス目でEntity/Relation本体を解析し、
  2パス目でPATCHブロックを検出して適用する。適用時、Patchの`was`値と
  Original Text側の現在値を比較し、一致すればPatchを適用、食い違えば
  **Conflict** として報告して**Patchを適用しない**（§18.4 Human-authored Data Wins）。
- Conflictはメニューの `Patches > Resolve Conflicts...` から解消できる:
  - **Keep Text**: Patchブロックを削除し、Original Textの値を正とする
  - **Apply Canvas Change**: Original Textの該当行をPatchの値で直接書き換え、
    不要になったPatchブロックを削除する（§11.3の `[Apply Canvas Change]` に対応）
  - **Merge**: OriginalとPatch、両方の値を提示したうえで、ユーザーが最終的に
    採用する値を自分で入力する（§11.3の `[Merge]`）。今回のConflictは
    Relationの単一フィールド(type等)の値の食い違いであり、複数行テキストの
    ような「部分的に両方を取り込む」自動マージには意味がないため、
    「OriginalでもPatchでもない第三の値」も選べる形にしている。
    入力した値はOriginal Textへ直接書き込まれ、Patchブロックは削除される。
  - **Open Diff**: OriginalとPatchの差分を表示してから、改めて選択させる
- CRDTによるリアルタイム共同編集（§11.4）はMVPでは未実装（plan.mdの方針どおり）。

## Timeline Lens（Phase 3）の使い方

- 画面下部の「Timeline Lens」パネルで「Timeline State を表示する」にチェックを入れると、
  Graph ViewがLive(現在の本文)ではなく、選択したtimestampのWorld State
  （`WorldStateEngine.state_at()`の結果）を表示するようになる。
- 「Add Event...」から、`entity_existence`（Entityの生死等）または`relation_status`
  （Relationのconfirmed/hypothetical/rumor）を変化させるEventを追加できる。
  対象はテキストから解析済みのEntity名・Relation ref_keyから選ぶ。
- スライダーを動かすと、その時点までのEventが適用されたWorld Stateが描画される。
  スライダー直下のChange Summaryには、その時点で発生するEventの
  「before → after」がテキストで表示される（Before/After Viewの最小版）。
- Layer Sliderの各チェックボックスでLayerごとにEntityの表示/非表示を切り替えられる。
  EntityにLayerを持たせるには、宣言時に `[名前:型:Layer]` と書く
  （例: `[A:Character:Su-ken]`）。Layer未指定のEntityは常に表示される。
- Timelineで追加したEventはテキストやCanonical Dataには一切保存されない
  （現状はアプリのセッション内メモリのみ。永続化は将来の拡張）。

## Worldbuilding Linter（Phase 4）の仕組み

画面下部の「Worldbuilding Linter」パネル（Timeline Lensとタブ切り替え）に、
再パースのたびに自動実行されたLint結果が一覧表示される。項目をダブルクリック
すると、対応する行がある場合エディタがその行にジャンプする。

集約している内容:
- **Parser issue**（未知のLayer、Patch対象が見つからない等）
- **Patch Conflict**（§11、Patches > Resolve Conflicts...で解消可能）
- **Ambiguity**（§15.6、Secondary Indexerの未解決参照・複数Entity曖昧文）
- **Temporal Contradiction**（§15.1、新規実装）: `entity_existence`が
  死亡系の値（dead/deceased/destroyed/died）になった後のtimestampで、
  そのEntityが別のEventに参加している場合に検出する。復活
  （existenceが非死亡値に戻る）があればその時点で区間を閉じる。
- **Relation Date Contradiction**（§15.3の最小版、新規実装）:
  Relationの`valid_from`/`valid_to`が両方とも数値として解釈でき、
  `valid_to < valid_from`になっている場合に検出する。
- **Missing Reference**（§15.4、新規実装）: `relation_add` Effectが、
  適用時点のWorld Stateに存在しないEntityを参照している場合に検出する。
- **Duplicate Entity**（§15.5、新規実装）: 同じ名前のEntityが異なる型で
  複数回明示宣言された場合に検出する（後発の宣言は無視され、その旨を通知）。

意図的に実装していないこと:
- **Membership Contradiction**（§15.2）: 「参加/離脱」を表す専用のEffect
  kind（例: `membership_join` / `membership_leave`）がまだ無く、現在の
  Event追加UIは`entity_existence`と`relation_status`のみをサポートしている。
  Effect語彙を拡張すれば同じ`core/linter.py`にチェックを追加できる設計。
- **一般的なRelation Contradiction**（§15.3）: 「対立」と「同盟」が同時に
  confirmedである、といった意味的な矛盾の検出には関係の対義語辞書のような
  ドメインオントロジーが必要で、plan.md自体もここは詳細化していないため、
  スキーマから機械的に判定できる日付の矛盾のみに絞っている。

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
[A:Character:Su-ken]
[B:Organization:Kan-ken]

[A:Character] -> [B:Organization] : 所属
A -> B : 対立
```

- `[名前:型]` または `[名前:型:Layer]` … Entity宣言（Layerは任意、§13参照）
- `[A:型] -> [B:型] : 関係名` … 型指定付きの明示的Relation
- `A -> B : 関係名` … 型指定なしのshorthand（既出のEntity名を参照。型は自動的に "Unknown" になり、後から `[A:型]` の宣言があれば確定します）
- `PATCH SourceName->TargetName#n: field = "value"  # was: "旧値"` … Canvas編集から生成されるPatch（§10.2, 通常は手で書かずGraph View経由で生成される）

File メニューから:
- Codex Syntaxテキストの読み込み/保存
- Canonical Data (Entity/Relation) のJSONエクスポート

Patches メニューから:
- Resolve Conflicts... （Patchのコンフリクト解消, §11）

## ディレクトリ構成

```
axral_codex/
├── main.py                 # アプリ本体 (Editor + Graph View + Timeline Lens + Linter)
├── core/
│   ├── models.py            # Canonical Data Model (Entity, Relation, WorldModel, Layer, Reference System)
│   ├── parser.py             # Primary Parser (Codex Syntax + PATCH + Duplicate Entity検出)
│   ├── indexer.py            # Secondary Indexer (自然言語→Candidate, Rule-based)
│   ├── events.py             # Event Schema
│   ├── world_state.py        # World State Engine (Initial State + Events, Snapshot)
│   └── linter.py             # Worldbuilding Linter (§15)
└── ui/
    ├── graph_view.py          # Graph Canvas (ドラッグ移動 + Relation編集)
    ├── candidate_panel.py      # Inline Suggestions / User Confirmation
    ├── timeline_panel.py       # Timeline Lens UI (スクラバー、Layer Slider、Event管理)
    └── linter_panel.py         # Linter結果パネル
```

## 次にやると良いこと（Phase 5以降）

1. Membership Contradiction（§15.2）向けに `membership_join` / `membership_leave`
   Effect kindを`core/events.py`・`core/world_state.py`に追加し、
   `core/linter.py`にチェックを実装する。
2. `core/indexer.py` のConfidence算出にEmbedding Signalを追加し（§4.5.1後半）、
   `confidence_breakdown`のembedding_signalフィールドを実際に埋める。
3. Timelineで追加したEventをCodex Syntaxとして本文に永続化する構文
   （例: `EVENT t=100 Death: A.existence = "dead"` のような形）を設計し、
   セッションをまたいでもEventが失われないようにする。
4. ノードを2枚並べるフル版のBefore/After View（現状はテキストサマリのみ）。
5. Incremental Parsing・Viewport Culling等のLarge Scale Performance対応（Phase 5、
   plan.md §12）。現状は全文を毎回再解析する素朴な実装。
