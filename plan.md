# Axral Codex 開発ロードマップ (plan.md v2)

> **v2 変更点サマリ**
> - Phase 0 を「MVP1に必要な最小Schema」と「完全版Schema」に分割し、着手順序を明確化 (§16.0)
> - Schemaのマイグレーション/バージョニング方針を追加 (§18.8)
> - Explicit Syntaxのオンボーディング/発見可能性のUX方針を追加 (§4.6)
> - Confidence Scoreの算出方針（ルールベース/LLM/ハイブリッド）を明記 (§4.5.1)
> - Reality vs Knowledge の将来拡張に備えたData Model上の拡張ポイントを明記 (§7.2.1)
> - その他は元のplan.mdを踏襲

---

## 1. Concept

**Axral Codex** は、「文章を書く」という自然な創作行為を、そのまま構造化された世界・設定データへ変換する **Worldbuilding Compiler / World State Engine** である。

Axral ecosystemにおいてCodexは作品制作の上流に位置し、

> **世界を記述する → 構造化する → 観測する → 検証する → 制作へ渡す**

という一連の流れを担う。

ただし、Codexは「自然言語を完全に理解するAI」を目指さない。

**明示的に記述された構造は確実に解釈し、自然言語から得られる情報は候補・補助情報として扱う。**

この境界をCodexの基本設計原則とする。

---

# 2. Core Philosophy

## 2.1 Text First

ユーザーの主要な入力手段は文章。

Markdown、自然言語、Codex専用構文を組み合わせ、設定を自由に記述できる。

```text id="0d6vkm"
A -> B : 対立
B -> C : 所属
A -> C : 尊敬
```

---

## 2.2 Explicit when Necessary

自然言語だけですべてを確定させようとしない。

重要な設定・関係性は、Codex Syntaxによって明示できる。

```text id="lpfy4b"
[A:Character] -> [B:Location]
```

あるいは、

```text id="h2afl0"
[A:Character] -> [B:Organization] : 所属
```

のように記述する。

### 原則

> **Explicit Syntax = Deterministic**

> **Natural Language = Probabilistic / Suggestive**

この2つを明確に分離する。

---

# 3. Canonical Data Model

Editor、Canvas、Timeline、LinterなどのUIをSource of Truthにしない。

すべての情報はCanonical Data Modelに集約する。

```text id="zz6f72"
                  ┌─────────────┐
                  │    Editor   │
                  └──────┬──────┘
                         │
                         ▼
              ┌────────────────────┐
              │  Canonical Data    │
              │     Model          │
              │   Source of Truth  │
              └───────┬─────┬──────┘
                      │     │
             ┌────────┘     └────────┐
             ▼                       ▼
       ┌──────────┐            ┌──────────┐
       │  Canvas  │            │ Timeline │
       └──────────┘            └──────────┘
```

---

# 4. Parser Architecture

## 4.1 Two-tier Parser Architecture

Parserを2系統に分離する。

```text id="g0t7mb"
                    Input
                      │
             ┌────────┴────────┐
             ▼                 ▼
      Codex Syntax         Natural Language
             │                 │
             ▼                 ▼
     Primary Parser      Secondary Indexer
             │                 │
       Deterministic       Probabilistic
             │                 │
             └────────┬────────┘
                      ▼
              Candidate / AST
                      │
                      ▼
             Canonical Data
```

---

## 4.2 Primary Parser

**Primary ParserはCodex Syntaxを担当する。**

目的は「賢く推測すること」ではなく、

**明示された構造を100%再現可能な形で解釈すること。**

### 対象

* Entity declaration
* Explicit Reference
* Relation
* Event
* Timeline
* Layer
* Attributes
* Status
* Explicit Type

### 例

```text id="51v9z5"
[A:Character] -> [B:Organization] : 所属
```

Primary Parserはこれを確定情報としてCanonical Dataへ変換する。

---

# 4.3 Secondary / Background Indexer

自然言語はSecondary / Background Indexerが解析する。

```text id="zw70bf"
AはBの組織に所属していた。
```

から、

```text id="8f4pif"
Candidate:
A -> B : 所属
confidence: 0.87
```

のような候補を生成する。

---

## 4.3.1 Candidate ≠ Fact

自然言語から抽出された情報は、ユーザーが承認するまで確定情報として扱わない。

```text id="o7g3li"
Candidate Relation
       ↓
User Review
       ↓
Confirmed Relation
```

これにより、LLM/NLPの誤認識によってCanonical Dataが破壊されることを防ぐ。

---

# 4.4 Background Processing

Secondary Indexerは入力処理のクリティカルパスから外す。

```text id="o0fajp"
User Typing
     ↓
Primary Parser
     ↓
Immediate UI Update
     
     ...background...

Secondary Indexer
     ↓
Candidate Suggestions
```

ユーザーの入力レスポンスをLLM/NLP処理に依存させない。

---

# 4.5 Natural Language Confidence

候補にはConfidenceを持たせる。

```text id="h8r67g"
confidence:
  high
  medium
  low
```

あるいは内部的には0〜1の数値を持つ。

ただし、Confidenceが高いことと「確定設定」であることは同義ではない。

---

## 4.5.1 Confidence算出方針 *(v2 追加)*

Confidence Scoreの出所を早期に固定しないと、後工程（コスト・レイテンシ・精度チューニング）で身動きが取れなくなるため、方針をここで明示する。

```text id="cf001a"
Confidence Source
 ├─ Rule-based Signal
 │    (Entity Type一致 / 直前参照 / Alias一致 など)
 ├─ Statistical / Embedding Signal
 │    (類似度・共起頻度)
 └─ LLM Signal
      (曖昧参照の解決・文脈推論)
```

### 方針

* **MVP2時点ではRule-based + 軽量Embedding Signalのみ**を採用し、LLM呼び出しは行わない（レイテンシとコストを抑え、Background Processingの原則§4.4を守るため）。
* LLM Signalは**Phase 1.5後半以降のオプション拡張**として位置づけ、Rule-basedスコアとは別レイヤーのSignalとして保持する（後から重み付け・A/Bテストできるように、単一のconfidence値に混ぜ込まない）。
* 各Candidateは`confidence_breakdown`として算出根拠（どのSignalがどの値を出したか）を保持し、UI上でユーザーに「なぜこの候補が出たか」を説明可能にする。これはLinter/Ambiguity Resolutionの信頼性にも直結する。

---

# 4.6 Explicit Syntaxの発見可能性とオンボーディング *(v2 追加)*

MVP1の成功条件は「この構文を書けば、必ず正しい図になる」というユーザーの信頼だが、これは**構文を知っていること**が前提になる。非エンジニアの創作者にとって`[A:Character] -> [B:Organization] : 所属`は初見のハードルになり得るため、以下をMVP1と同時に用意する。

* **Live Preview**: Codex Syntaxを書いている最中、その場でミニGraphプレビューを表示し、「書いたら何が起きるか」を即座に見せる。
* **Slash / Auto-insert Template**: `/relation`のようなショートカットでEntity/Relation構文のテンプレートを挿入できるようにする。
* **自然文→構文への昇格導線を可視化**（§5.3の技術自体は既存設計通り。UI上でも「この文を確定構文に変換しますか？」という1クリック導線を明示する）。

この節はUI実装の詳細ではなく、**MVP1のスコープにオンボーディングUXを含める**という優先順位の明記が目的である。

---

# 5. Ambiguity Resolution

自然言語では、

* 同姓同名
* 類似用語
* 指示語
* 主語省略
* 文脈依存参照
* Entity Typeの曖昧性

が発生する。

---

## 5.1 Automatic Resolution

Parser / Indexerは以下を利用して候補を絞り込む。

* Section
* Entity Type
* 文脈
* 直前の参照
* Relation Type
* Layer
* Timeline
* Alias
* User history

確信度が十分高い場合は候補を上位表示する。

ただし、重要な設定を無断で確定しない。

---

## 5.2 Interactive Disambiguation

曖昧な参照はInline Completionで提示する。

```text id="zxj8uo"
AはBに向かった。
   ↑

B [Character]
B [Location]
B [Organization]
```

ユーザーは1キーまたはクリックで選択できる。

---

## 5.3 Explicit Resolution

ユーザーが曖昧性を確実に解消したい場合、

```text id="iq1z0p"
[A:Character]
```

のような明示指定を利用できる。

これにより、

> **曖昧な自然言語 → 明示構文**

へのシームレスな昇格を可能にする。

---

# 6. Entity Model

```text id="v0nqyk"
Entity
 ├─ id
 ├─ type
 ├─ name
 ├─ aliases[]
 ├─ layer
 ├─ attributes
 ├─ existence
 ├─ source_refs[]
 ├─ schema_version   ← (v2 追加)
 └─ metadata
```

`source_refs[]`によって、

> このEntityがどの文章・どの記述から生成されたか

を追跡可能にする。

`schema_version`は§18.8のマイグレーション方針に対応するためのフィールドで、Entity単位でどのSchema世代で作成/更新されたかを追跡する。

---

# 7. Relation Model

```text id="lnx9jt"
Relation
 ├─ id
 ├─ source
 ├─ target
 ├─ type
 ├─ status
 ├─ valid_from
 ├─ valid_to
 ├─ source_refs[]
 ├─ schema_version   ← (v2 追加)
 └─ metadata
```

---

# 7.1 Relation Status

RelationはTrue / Falseではなく、認識状態を持つ。

```text id="wq2pzi"
confirmed
hypothetical
rumor
```

### confirmed

確定した設定。

### hypothetical

仮説・未確定。

### rumor

世界内で噂として存在する情報。

Canvasでは、

```text id="6muv0f"
confirmed     ─────────
hypothetical  - - - - -
rumor         · · · · ·
```

などで視覚的に区別する。

---

# 7.2 Reality vs Knowledge

将来的に、

> 実際にはAとBは親子だが、登場人物はそれを知らない

という状態を表現できるようにする。

```text id="3b9xq4"
Reality State
Knowledge State
```

を将来的に分離可能な設計とする。

---

## 7.2.1 拡張ポイントの事前確保 *(v2 追加)*

これはPhase 3以降の機能だが、後付けでData Modelを壊さないために、**Phase 0の時点でRelationに`perspective`フィールド（デフォルト値`objective`）を予約しておく**。

```text id="7p3rvz"
Relation
 └─ perspective: "objective" (default)
             ↳ 将来的に "knowledge_of:<entity_id>" 等の値を許容する拡張点
```

実装は不要だが、フィールドとマイグレーションパスの存在だけをPhase 0のSchema設計時に確保しておくことで、Phase 3でのRelation Model全面改修を回避する。

---

# 8. Event Model

```text id="hwwa3j"
Event
 ├─ id
 ├─ timestamp
 ├─ type
 ├─ participants[]
 ├─ effects[]
 └─ metadata
```

EventはWorld Stateを変化させる。

---

# 9. World State Architecture

World StateはEvent履歴から再構築できる。

```text id="hfrh0b"
Initial State
     +
Events
     ↓
World State
```

ただし、大規模データでは毎回Initial Stateから全Eventを再生しない。

---

# 9.1 Snapshotting Strategy

Timeline Lensの高速化のため、特定時点のWorld StateをSnapshotとしてキャッシュする。

```text id="2ibpdx"
Initial
   │
Events
   │
   ▼
Snapshot A
   │
Events
   │
   ▼
Snapshot B
   │
Events
   │
   ▼
Current State
```

---

## 9.1.1 Snapshot Points

Snapshot候補：

* Tear
* Major Event
* Chapter boundary
* User-defined Key Event
* 一定数のEvent経過後

---

## 9.1.2 Timeline Query

例えばTear後のWorld Stateを表示する場合、

```text id="1u6vje"
Nearest Snapshot
      ↓
Replay remaining Events
      ↓
Target World State
```

とする。

これによりTimeline移動時の計算量を抑える。

---

## 9.1.3 Snapshot Invalidation

過去Eventが変更された場合、そのEvent以降のSnapshotを無効化する。

```text id="b50c9q"
Event 100 changed
     ↓
Invalidate
Snapshot 101
Snapshot 102
Snapshot 103
     ↓
Rebuild lazily
```

必要なSnapshotのみ再構築する。

---

# 10. Non-destructive Text Sync

CanvasからTextへの逆反映では、ユーザーの文章を破壊しない。

**Human-authored Textは不可侵。**

---

## 10.1 Generated Section

Canvas由来の変更は専用セクションへ保存する。

```markdown id="f4x6p4"
# Characters

A
B
C

AとBは幼少期からの知人である。

# Generated Relations

A -> B : 対立
B -> C : 所属
```

---

## 10.2 Patch-style Sync

既存Relationの変更はPatchとして記録可能にする。

```text id="5z1aoh"
# Generated Relations

PATCH rel_024:
  type = "協力"
```

Original Textを書き換えない。

---

# 11. Canvas ↔ Text Conflict Resolution

CanvasとEditorが同じ情報を異なる方法で変更した場合、Conflictを明示的に扱う。

---

## 11.1 Source Priority

基本原則：

```text id="j1u9i7"
Human-authored Explicit Text
          >
Generated Patch
          >
AI/NLP Candidate
```

つまり、

**人間が明示的に書いた情報を最優先する。**

---

## 11.2 Conflict Example

Original:

```text id="l5a2jg"
A -> B : 対立
```

Canvas:

```text id="j6asww"
PATCH:
A -> B : 協力
```

この場合、自動的に既存本文を変更しない。

Linterが、

```text id="5knqfw"
⚠ Conflict detected

Original:
A -> B : 対立

Generated Patch:
A -> B : 協力
```

と通知する。

---

## 11.3 Resolution UI

ユーザーに、

```text id="u9g2mg"
[Keep Text]
[Apply Canvas Change]
[Merge]
[Open Diff]
```

を提示する。

ユーザーが明示的に選択した場合のみCanonical Dataを更新する。

---

## 11.4 CRDT

将来的に複数人編集・リアルタイム共同編集が必要になった場合、CRDTなどのConflict-free同期モデルを検討する。

ただしMVPではCRDTを必須要件としない。

まずは、

**Explicit Source Priority + Patch + Diff + User Resolution**

を基本とする。

---

# 12. Large Scale Performance

数十万文字〜数千Entity〜数万Event規模を想定する。

---

## 12.1 Incremental Parsing

全文を毎回解析しない。

```text id="iqy3mt"
Document
 ├─ Section A
 ├─ Section B  ← editing
 ├─ Section C
 └─ Section D
```

変更されたSection / Paragraphのみを再解析する。

---

## 12.2 Dependency-aware Recalculation

変更されたEntityを起点として、

```text id="1o4q56"
Changed Entity
      ↓
Affected Relations
      ↓
Affected Events
      ↓
Affected World States
      ↓
Affected Lint Results
```

のみを再計算する。

---

## 12.3 Viewport Culling

Infinite Canvasでは画面外Nodeを常時フルレンダリングしない。

基本的に、

```text id="o8f30w"
Viewport
+
Selected Entity
+
N-hop Neighborhood
```

を優先描画する。

---

## 12.4 Progressive Rendering

描画優先順位：

1. Viewport内Node
2. 直接Relation
3. N-hop Node
4. 遠方Node
5. 補助情報

---

## 12.5 Lazy Loading

巨大World Graphは必要な範囲だけロードする。

```text id="76eq1s"
Project
 ├─ World
 ├─ Characters
 ├─ Organizations
 ├─ Timeline
 └─ Relations
```

各データセットを必要に応じて遅延ロードする。

---

# 13. Layer System

```text id="d2br5s"
        Su-ken
          │
       Kan-ken
          │
       An-ken
          │
       Ki-ken
```

Layer Sliderによって、

* Highlight
* Transparency
* Filtering
* Layer-specific Layout
* Layer Relations

を切り替える。

Layerは単なるCategoryではなく、**世界を観測するための次元**として扱う。

---

# 14. Timeline Lens

Timelineを移動するとWorld Stateを変更する。

```text id="0ipk1a"
                Tear
                  ↓
───────●─────────●────────────
       Before           After
```

変化対象：

* 所属
* 生死
* Relation
* Ownership
* Organization
* World State

---

# 15. Worldbuilding Linter

## 15.1 Temporal Contradiction

```text id="2g8fms"
A died in 120
A joined Organization X in 150
```

↓

```text id="2q7d8n"
⚠ A is already dead at this point.
```

---

## 15.2 Membership Contradiction

```text id="f5q09h"
A joined X : 200
A left X   : 180
```

---

## 15.3 Relation Contradiction

論理的に成立しないRelationを検出。

---

## 15.4 Missing Reference

存在しないEntityへの参照。

---

## 15.5 Duplicate Entity

同一Entityの重複定義。

---

## 15.6 Ambiguity

```text id="n4o9wm"
ℹ Unresolved Reference
```

として扱う。

曖昧性そのものをErrorにしない。

---

# 16. Development Phases

## 16.0 実装順序に関する注記 *(v2 追加)*

Phase 0を「フルスペックのSchema」として一度に作り切ろうとすると、MVP1着手までの初期コストが膨らむ。そのため、Phase 0を以下の2段階に分割して実装する。

```text id="ph0split"
Phase 0a — MVP1 Minimal Schema
 ├─ Entity Schema (最小: id, type, name, source_refs)
 ├─ Relation Schema (最小: id, source, target, type, source_refs)
 ├─ Stable ID
 └─ Serialization

Phase 0b — Full Foundation
 ├─ Event Schema
 ├─ World State
 ├─ Reference System (Alias含む)
 ├─ Layer
 ├─ Timeline
 ├─ Relation Status
 └─ schema_version / perspective 等の拡張フィールド
```

Phase 0aのみでMVP1（Explicit Text → Graph）に着手可能とし、Phase 0bはMVP3/MVP4で必要になる要素から順次実装する。これにより「Phase 0が終わるまで何も動くものがない」状態を避ける。

---

## Phase 0 — Canonical Data Foundation

### 実装

* Entity Schema
* Relation Schema
* Event Schema
* World State
* Stable ID
* Reference System
* Layer
* Timeline
* Relation Status
* Serialization
* Source References
* schema_version フィールド *(v2 追加, §18.8参照)*
* perspective 拡張ポイント *(v2 追加, §7.2.1参照)*

### Goal

すべてのUIが共通のCanonical Dataを操作できる基盤を完成させる。

実装順序は§16.0のPhase 0a / 0b分割に従う。

---

# Phase 1 — Deterministic Codex Parser

### 実装

* Markdown Parser
* Codex Syntax
* Tokenizer
* AST
* Explicit Entity Declaration
* Explicit Relation
* Explicit Event
* Stable Reference
* Syntax Highlighting
* Basic Validation
* Live Preview / Template Insertion *(v2 追加, §4.6参照)*

### Goal

**「明示的に書いた構造は、確実にデータになる」**

かつ**「その構文をユーザーが迷わず発見・習得できる」**ことをGoalに含める。

---

# Phase 1.5 — Background Semantic Indexer

### 実装

* Natural Language Extraction
* Entity Candidate Detection
* Relation Candidate Detection
* Reference Candidate Detection
* Confidence Score (Rule-based → Embedding → LLM の段階導入, §4.5.1参照)
* Ambiguity Detection
* Inline Suggestions
* User Confirmation

### Goal

**「自然文から設定候補が浮かび上がる」**

ただしPrimary Parserとは完全に分離する。

LLM Signalの導入はこのPhase後半のオプションとし、まずRule-based Confidenceのみで動くMVP2を先に成立させる。

---

# Phase 2 — Graph Canvas

### 実装

* Infinite Canvas
* Node / Edge Rendering
* Auto Layout
* Graph Editing
* Canvas → Data
* Data → Canvas
* Non-destructive Text Sync
* Generated Relations
* Patch System
* Conflict UI
* Undo / Redo

### Goal

**「書いた世界が図になる」**

---

# Phase 3 — World Dimension

### 実装

* Layer Slider
* Timeline
* Event Effects
* World State Reconstruction
* Snapshotting
* Snapshot Invalidation
* Before / After View
* Layer × Time
* Reality vs Knowledge の本実装 (§7.2.1のperspective拡張点を利用)

### Goal

**「世界を時間と階層から観測する」**

---

# Phase 4 — Worldbuilding Compiler

### 実装

* Temporal Linter
* Relation Linter
* Membership Linter
* Existence Linter
* Reference Linter
* Rule Engine
* Dependency Graph
* Contradiction Detection
* Uncertainty Handling

### Goal

**「世界観そのものを検証する」**

---

# Phase 5 — Large Scale Optimization

### 実装

* Incremental Parsing
* AST Diff
* Dependency-aware Recalculation
* Viewport Culling
* Progressive Rendering
* Lazy Loading
* Graph Clustering
* Background Workers
* Cached World State
* Snapshot Optimization

### Goal

大規模World Graphでも、入力・Canvas・Timelineのレスポンスを維持する。

---

# Phase 6 — Axral Studio Integration

Axral CodexをAxral ecosystemの上流システムとして接続する。

```text id="kq67vy"
                    Axral Codex
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
    Character          World             Lore
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                   Axral Studio
                         │
                   Script / Scene
                         │
                         ▼
                    Audio / Video
```

### 実装

* Character Export
* Dialogue Export
* Scene Metadata
* Lore Export
* Script Integration
* API
* Import / Export
* Cross-reference

### 原則

**Codex = upstream**

**Studio = downstream**

---

# 17. MVP Strategy

## MVP 1 — Explicit Text → Graph

最初はAI/NLPに依存しない。

```text id="e99qiu"
[A:Character] -> [B:Organization] : 所属
```

↓

```text id="7n7y0w"
A ──所属──> B
```

### 成功条件

ユーザーが、

> 「この構文を書けば、必ず正しい図になる」

と信頼できること。

**かつ**、その構文をLive Preview / Template挿入なしに探し当てなくても迷わず使い始められること *(v2 追加, §4.6)*。

---

# MVP 2 — Natural Language Suggestions

```text id="bq9t3d"
AはBの組織に所属していた。
```

↓

```text id="w2n6c1"
Candidate:

A [Character]
   └─ 所属 → B [Organization]

[Accept] [Edit] [Ignore]
```

自然言語解析はあくまで補助機能として提供する。

Confidence算出はRule-based + 軽量Embeddingのみで開始する *(v2 追加, §4.5.1)*。

---

# MVP 3 — Structured World

追加：

* Stable ID
* Entity Editing
* Graph Editing
* Reference
* Relation Status
* Non-destructive Sync
* Conflict Detection

---

# MVP 4 — World State

追加：

* Event
* Timeline
* Layer
* World State
* Snapshot
* Temporal Linter

---

# 18. Data Integrity Principles

## 18.1 Never Destroy Human-authored Text

人間が書いた文章を自動処理によって破壊しない。

---

## 18.2 Never Guess Silently

曖昧な情報を勝手に確定しない。

---

## 18.3 Explicit Syntax Wins

明示的なCodex Syntaxを自然言語候補より優先する。

---

## 18.4 Human-authored Data Wins

人間が明示的に書いた設定は、Machine-generated Patchより優先する。

---

## 18.5 Preserve Uncertainty

仮説・噂・未確定情報をそのまま保持する。

---

## 18.6 Preserve History

変更はEvent / Patch / Revisionとして追跡可能にする。

---

## 18.7 Separate Human Intent from Machine Structure

```text id="n5zjlh"
Human-authored Text
        +
Explicit Codex Syntax
        +
Machine-generated Candidates
        +
User-approved Resolution
        +
Generated Patches
```

を論理的に分離する。

---

## 18.8 Schema Versioning & Migration *(v2 追加)*

Canonical Data ModelはSource of Truthである以上、スキーマ変更が既存プロジェクトのデータを破壊してはならない。

### 方針

* すべてのEntity / Relation / Eventは`schema_version`フィールドを持つ（§6, §7）。
* Schema変更は**破壊的変更を原則禁止**し、フィールド追加はデフォルト値付きのOptionalとする。
* 破壊的変更が避けられない場合は、Migration Scriptを「読み込み時に旧バージョンを新バージョンへ変換するAdapter」として実装し、ユーザーの元データ（Human-authored Text）自体には触れない。
* Migration実行前に必ずバックアップ／Undo可能なスナップショットを取る（§9.1のSnapshot機構を流用可能）。

この方針をPhase 0の時点で確定させることで、Phase 3〜4でのRelation/Event拡張時にデータ移行コストが破綻しないようにする。

---

# 19. Architecture Principles

Axral Codexの実装では、以下を最上位原則とする。

### 19.1 Deterministic Core

Codexの中心部分は決定論的であること。

---

### 19.2 Probabilistic Edge

AI/NLPは候補生成・補助・検索に利用する。

---

### 19.3 Human-in-the-loop

重要な曖昧性・Conflict・設定確定はユーザーが最終決定する。

---

### 19.4 Event-driven World

世界の変化をEventとして表現する。

---

### 19.5 Snapshot-assisted Reconstruction

Event Sourcingを維持しつつ、Snapshotによって高速化する。

---

### 19.6 Patch-based Synchronization

Human-authored Textを保護し、Machine-generated変更をPatchとして分離する。

---

### 19.7 Incremental Everything

可能な限り、

* Parsing
* Validation
* Rendering
* State Reconstruction
* Indexing

をIncrementalにする。

---

### 19.8 Schema Stability *(v2 追加)*

Canonical Data Modelのスキーマ変更は非破壊的であることを原則とし、拡張は常にOptional Field + Migration Adapterで行う（§18.8参照）。

---

# 20. Final Product Vision

ユーザーはCodexを「設定資料を整理するソフト」として使わない。

世界について文章を書く。

```text id="5jly0h"
AはTear以前、Bの組織に所属していた。
しかしTearの後、Bと対立するようになった。
```

Codexは自然文から候補を抽出する。

```text id="pp5g7q"
Candidate Relations

A ──所属──> B
A ──対立──> B

[Accept]
```

ユーザーが承認するとCanonical Dataへ反映される。

明示構文なら、

```text id="g0g7z1"
[A:Character] -> [B:Organization] : 所属
```

即座に確定する。

そしてTimelineを動かすと、

```text id="b0z1aw"
             BEFORE TEAR

A ───── 所属 ─────> B


                    TEAR
                     ↓


             AFTER TEAR

A ───── 対立 ─────> B
```

というWorld Stateの変化として表示される。

さらに、

```text id="rx2jvz"
⚠ Timeline contradiction
ℹ B's identity unresolved
✓ Relation transition detected
```

のように世界の整合性を検証する。

---

# 21. Product Definition

> **Axral Codexは、文章を書くことで世界を構築し、その世界を構造化し、時間と階層を越えて観測し、不確実性と矛盾を管理し、最終的に作品制作へ接続するWorldbuilding Compilerである。**

その核心は、

**「AIが勝手に設定を作ること」ではない。**

人間が書いた世界を、

**壊さず、誤魔化さず、構造化し、必要なときだけAIに補助させること。**

明示された構造には決定性を。

自然言語には柔軟性を。

曖昧性にはユーザーの選択権を。

変更には履歴を。

大規模データにはIncremental Processingを。

そして世界には、**時間と状態という概念を持たせる。**

それがAxral Codexのアーキテクチャ原則である。


---

# 22. Usability & Cross-Platform UX Roadmap (v3)

本章は、既存のCodexアーキテクチャとMVPロードマップを維持したまま、Web版・デスクトップ版の使いやすさを段階的に改善するための計画である。

実装の有無はリポジトリごとに異なる可能性があるため、着手時に現状を確認し、実装済みの項目は再実装せず検証・改善に回す。

## 22.1 Goals

- 初めて使うユーザーが、Codex Syntaxを知らなくても最初の設定データを作成できる。
- Text Editor、Graph、Timeline、Candidate、Linterが、同じCanonical Data Modelを一貫して表示・編集する。
- 編集内容・ノード配置・タイムラインイベントが、明示的に保存され、再起動後も復元される。
- 変更の取り消し・やり直しができ、誤操作による設定消失を防ぐ。
- 小規模な設定から大規模な世界設定まで、検索・絞り込み・表示性能を段階的に拡張できる。
- Web版とデスクトップ版でデータ形式・操作結果・検証ルールを一致させつつ、各環境に適したUIを提供する。

## 22.2 Design Principles

### 22.2.1 Shared Core, Platform-Specific UI

Parser、Canonical Data Model、Validation、Timeline/World Stateの意味論、保存形式を可能な限り共有する。プラットフォーム差は入力方法・画面構成・ファイルアクセス・実行環境の層で吸収する。

### 22.2.2 Safe Editing

ユーザーが書いたテキストを無断で書き換えない。Canvasからの変更は差分として示し、適用前に確認できるようにする。破壊的な操作にはUndo、Redo、確認、または復元手段を用意する。

### 22.2.3 Discoverable Syntax

Codex Syntaxを前提知識にしない。構文例、入力補完、エラー位置、修正例、クリック可能なヘルプを段階的に提供する。自然言語候補は確定データと明確に区別する。

### 22.2.4 Consistent Feedback

保存中・保存済み・未保存・競合・解析中・エラー・警告を視覚的に区別し、処理が止まっているのか、待機中なのかをユーザーが判断できるようにする。

## 22.3 Phase U0 — Cross-Platform Audit

**目的:** 実装済み機能と実際の挙動を確認し、共通課題とプラットフォーム固有課題を分ける。

- [ ] Web版・デスクトップ版の起動方法、フレームワーク、対応OS／ブラウザ、画面構成を確認する。
- [ ] 各画面（Editor、Graph、Timeline、Candidate、Linter、Save/Load）の実装状況を一覧化する。
- [ ] 同じ入力データを両版で開き、Parser結果・Entity/Relation数・警告・保存結果を比較する。
- [ ] 保存対象（本文、Canonical Data、イベント、ノード位置、表示設定）と復元可否を確認する。
- [ ] キーボード、マウス、タッチ操作、狭い画面での操作性を確認する。
- [ ] 現状のテスト・既知不具合・未実装項目を記録し、実装済み機能を重複開発しない。

**完了条件:** 共通課題／Web固有課題／デスクトップ固有課題／要調査事項を分けた監査表がある。

## 22.4 Phase U1 — Core Editing Safety

**優先度: P0**

- [ ] Undo / Redoを導入し、テキスト編集・Canvas編集・イベント編集を一貫した履歴として扱う。
- [ ] 保存状態を表示する（未保存、保存中、保存済み、保存失敗）。
- [ ] 保存失敗時に理由を表示し、入力内容を失わない復旧経路を用意する。
- [ ] TextとGraphの同期競合について、差分と適用対象を明示する。
- [ ] 大きな変更を適用する前に、変更内容・影響範囲をプレビューできるようにする。
- [ ] ノード位置などの編集補助情報について、保存するもの／再生成するものを定義する。

**完了条件:** 主要な編集をUndo/Redoでき、保存・再読み込み後に確定済みの変更が失われない。競合をユーザーが理解して解決できる。

## 22.5 Phase U2 — Onboarding & Syntax Assistance

**優先度: P0**

- [ ] 新規プロジェクト用のサンプルと空状態ガイドを用意する。
- [ ] 最初のEntity・Relationを作る短いチュートリアルを提供する。
- [ ] Codex SyntaxのクイックリファレンスをEditorから開けるようにする。
- [ ] Parserエラーに行番号・該当箇所・原因・修正例を表示する。
- [ ] Entity名・型・Layer・Relationの候補を補完候補として表示する。
- [ ] Candidateの「採用／無視」操作に、候補の根拠と対象行を表示する。
- [ ] 日本語UIを基本とし、英語ラベル・ボタン・ダイアログの表記を統一する。

**完了条件:** 初見のユーザーがサンプルを参考にEntityとRelationを追加し、エラーを自力で修正できる。

## 22.6 Phase U3 — Navigation & Information Density

**優先度: P1**

- [ ] Entity、Relation、Eventを横断する検索を追加する。
- [ ] 型・Layer・Relation Status・警告状態で絞り込めるようにする。
- [ ] 検索結果を選択したとき、Editorの該当箇所とGraphの対象ノードを同期して強調する。
- [ ] 選択中のEntity／Relationの詳細をInspectorに集約し、属性編集の導線を明確にする。
- [ ] Editor／Graph／Timeline／Inspectorの表示幅を調整・折りたたみできるようにする。
- [ ] 空状態、検索結果ゼロ、解析エラー、読み込み中の各状態を設計する。
- [ ] Graphの選択状態・ズーム・パン・フィルタを、不要な再描画で失わないようにする。

**完了条件:** Entity数が増えても、検索から対象の確認・編集まで少ない操作で到達できる。

## 22.7 Phase U4 — Timeline Persistence & Clarity

**優先度: P0（イベントが未永続化の場合）**

- [ ] Timeline Eventの保存形式とCanonical Data Modelとの関係を確定する。
- [ ] Eventの追加・編集・削除をUndo/Redo履歴に含める。
- [ ] Eventの日時・対象Entity/Relation・効果・有効範囲を一覧で確認できるようにする。
- [ ] 現在時点と変更前後のWorld Stateを視覚的に比較できるようにする。
- [ ] Layer FilterとTimelineの状態が、GraphやLinterの表示にどう影響するかを明示する。
- [ ] Eventの競合・無効な参照・時系列矛盾を、原因箇所へのリンク付きで示す。

**完了条件:** Eventを保存・再読込しても状態が再現され、Timeline操作がEditor／Graph／Linterと矛盾しない。

## 22.8 Phase U5 — Web-Specific UX

**対象:** ブラウザで実行するWeb版。実際の配信形態・技術構成はPhase U0で確認する。

- [ ] デスクトップ幅では主要パネルを並列表示し、狭い幅ではタブ／ドロワーなどに切り替える。
- [ ] タブレットでEditorとGraphを行き来しやすいレイアウトを用意する。
- [ ] スマートフォンでは閲覧・検索・軽微な編集を優先し、複雑な多画面操作を無理に詰め込まない。
- [ ] タッチ操作のターゲットサイズ、スクロール方向、ズーム／パンの競合を確認する。
- [ ] ブラウザ更新・タブ終了・ネットワーク断に備え、ローカル下書きや復旧可能な保存方式を検討する。
- [ ] 大きなGraphでメインスレッドを長時間ブロックしないよう、処理時間とメモリ使用量を計測する。
- [ ] ブラウザ内保存・サーバー保存を採用する場合、同期状態と競合時の挙動を明示する。

**完了条件:** デスクトップ／タブレット／スマートフォンの各幅で、主要な閲覧・編集フローが破綻せず、未保存データの復旧方針が明確である。

## 22.9 Phase U6 — Desktop-Specific UX

**対象:** ネイティブのデスクトップ版。実際のフレームワークとOS対応はPhase U0で確認する。

- [ ] 新規・開く・保存・別名保存・エクスポートの導線を統一する。
- [ ] 標準的なショートカット（保存、Undo/Redo、検索、選択解除）を実装し、メニューに表示する。
- [ ] ファイルの未保存変更がある状態で閉じる場合、保存／破棄／キャンセルを選べるようにする。
- [ ] ウィンドウサイズ・パネル幅・表示設定を保存し、次回起動時に復元する。
- [ ] OSのファイル選択、ドラッグ＆ドロップ、複数ウィンドウ対応の必要性を評価する。
- [ ] 大規模プロジェクトでの起動・解析・保存・Graph操作を計測し、UIフリーズを防ぐ。

**完了条件:** 日常的なファイル編集がキーボード中心でも行え、ウィンドウ再起動後に作業環境を復元できる。

## 22.10 Phase U7 — Performance & Accessibility

**優先度: P1〜P2**

- [ ] Parser、Linter、Graph描画、World State再構築の処理時間を計測する。
- [ ] 必要に応じて差分解析、増分Lint、Snapshot、キャッシュを導入する。
- [ ] GraphのViewport Cullingや可視範囲ベース描画を評価する。
- [ ] 解析中の進捗・キャンセル・完了状態を表示する。
- [ ] 色だけに依存せず、Relation StatusやLint Severityを文字・線種・アイコンでも識別できるようにする。
- [ ] キーボード操作、フォーカス順序、コントラスト、スクリーンリーダー向けラベルを確認する。
- [ ] 小・中・大規模の代表データを用意し、性能回帰テストを追加する。

**完了条件:** 代表データで性能を測定でき、主要操作が応答性を保ち、重要な状態を色以外でも識別できる。

## 22.11 Phase U8 — Cross-Platform Parity & Release Gate

- [ ] 共通フィクスチャを使って両版のParser・Canonical Data・Linter結果を比較する。
- [ ] 保存→再読込、Undo/Redo、Conflict Resolution、Timeline Eventのテストを両版で実施する。
- [ ] 画面構成は異なっても、同じ操作が同じデータ結果を生むことを確認する。
- [ ] 片方の版でしか使えない機能は、UI上で明示するか、共通対応まで非表示にする。
- [ ] 新機能は、正常系・異常系・空データ・大規模データのテストを含める。
- [ ] READMEの機能表と実装状況を同期する。

**リリース条件:**
1. データの保存・再読込で確定済みの情報が失われない。
2. Undo/Redoが主要な編集操作で一貫して動作する。
3. 同じ入力に対して両版のCanonical DataとLint結果が一致する。
4. 未保存・競合・エラーがユーザーに分かる形で表示される。
5. 主要フローを自動テストと手動チェックリストで再現できる。

## 22.12 Recommended Implementation Order

1. **U0: 監査** — 両版の実装・保存・テスト状況を確認する。
2. **U1: 編集の安全性** — 保存状態、Undo/Redo、Conflict、復旧。
3. **U2: 初心者支援** — サンプル、構文ヘルプ、エラー修正、表記統一。
4. **U4: Timeline永続化** — 未保存イベントがある場合はU1と並行して優先。
5. **U3: 検索とナビゲーション** — 大規模設定でも目的の情報に到達できるようにする。
6. **U5/U6: プラットフォーム別改善** — Webのレスポンシブ対応、Desktopの作業効率。
7. **U7: 性能・アクセシビリティ** — 計測結果に基づいて最適化する。
8. **U8: 両版の一致確認** — リリース前の回帰テストを必須にする。

### Scope Control

- 大規模な全面書き換えを最初の手段にしない。既存のCanonical Data ModelとParserを維持し、小さな変更単位で改善する。
- 監査で未実装と確認できた項目だけを実装タスク化する。
- UI改善のために決定論的Parserや既存のデータ形式を不用意に変更しない。
- AIによる自動確定を追加する場合も、ユーザー確認と元テキスト保護を維持する。
- 完了判定は「コードを書いた」ではなく、テストとユーザー操作の結果で行う。
