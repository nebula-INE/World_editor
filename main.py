"""
Axral Codex - MVP1 "Explicit Text -> Graph" (plan.md v2 準拠)

対応スコープ:
  - Phase 0a: Entity / Relation の最小Canonical Data Model (core/models.py)
  - Phase 1 : Codex Syntaxの決定論的Primary Parser (core/parser.py)
  - Phase 1 : Live Preview (§4.6) — 入力から即座にGraphへ反映
  - Phase 1.5: Secondary Indexer (自然言語→Candidate, core/indexer.py) と
               Inline Suggestions / User Confirmation UI (ui/candidate_panel.py)
  - Phase 2 : Graph Canvas — ノードのドラッグ移動、Relationラベル編集からの
              Patch発行、Non-destructive Text Sync (Generated Section + PATCH,
              §10.1/§10.2)、Conflict検出とResolution UI (§11)

意図的にスコープ外にしているもの (plan.mdの原則に従い、後続Phaseへ):
  - Embedding Signal / LLM Signal によるConfidence算出 (§4.5.1、Phase 1.5後半)
  - Infinite Canvas最適化・Undo/Redo (Phase 2の残り・Phase 5)
  - Timeline / Layer / World State操作UI (Engine自体はPhase 0bで実装済み。
    Timelineスクラバー等のUIはPhase 3)
  - Linter (Phase 4)

--- Phase 2 追記 ---------------------------------------------------------
Canvas → Patch → Conflict のフロー:
  1. GraphView上でRelationラベルをダブルクリックすると
     `relation_type_edit_requested(ref_key, old_type, new_type)` が発行される。
  2. `_edit_relation_type()` が「# Generated Relations」内に
     `PATCH <ref_key>: type = "<new_type>"  # was: "<old_type>"` を書き込む
     (Original Textの該当行そのものは一切書き換えない, §18.1)。
  3. 再パース時、Primary Parserがこの"was"値と現在のOriginal Text側の値を
     比較する。一致すればPatchを適用、食い違えば§11のConflictとして報告する
     (Human-authored Text > Generated Patch, §18.4)。
  4. Conflictが検出されると、メニューの「Patches > Resolve Conflicts...」から
     [Keep Text] [Apply Canvas Change] [Merge] [Open Diff] を選んで解消できる。
     [Merge] は単一フィールドの値の食い違いに対し、ユーザーが最終値を
     自分で入力する形で実装している (§11.3、詳細はREADME参照)。
---------------------------------------------------------------------------

Background Processing (§4.4) の原則に対応し、Primary Parserは
QTimerによる短いデバウンス後にのみ実行する。パース自体はまだ軽量な
正規表現ベースなのでUIスレッドで十分間に合うが、Secondary Indexerを
追加する際はここをQThread/Workerへ切り出す前提の構成にしてある。

--- Phase 1.5 追記 -----------------------------------------------------
Secondary Indexer (core/indexer.py) をここで接続する。
  - Primary Parserの結果 (natural_lines) だけを入力にし、Candidateを生成する
    (Primary Parser完了後に呼ぶ。§4.3の分離を維持)。
  - CandidateはCandidatePanelにInline Suggestionsとして表示するのみで、
    Canonical Dataには一切書き込まない (§4.3.1 Candidate ≠ Fact)。
  - Accept時は、Canonical Dataを直接いじるのではなく
    「# Generated Relations」セクションへ確定Codex Syntax行を追記し、
    それをPrimary Parserに再解釈させる (§10.1 Generated Sectionの考え方)。
    これによりCandidate確定の経路も「明示構文は確実にデータになる」という
    MVP1の原則(§18.3 Explicit Syntax Wins)に統一される。
  - Ignore時はCanonical Dataにもテキストにも触れず、セッション内でのみ
    再表示を抑制する(ignored_signaturesで管理)。
-------------------------------------------------------------------------

--- Phase 3 追記 ---------------------------------------------------------
Timeline Lens (§14) UIを接続する。
  - WorldStateEngine (core/world_state.py, Phase 0bで実装済み) の
    Initial Stateは、再パースのたびに `set_initial_model()` で最新化する。
    これにより本文編集とTimeline Engineが常に同期する。
  - EventはTimelinePanelの「Add Event...」ダイアログから追加する。
    対応するEffect kindは entity_existence / relation_status の2種類のみ
    (最小構成。relation_add等はEngine側には実装済みだがUIはまだ無い)。
  - Layer Slider (§13) のチェック状態はGraphView.render_model()の
    visible_layers引数にそのまま渡す。EntityへのLayer割り当ては
    Entity宣言構文の拡張 `[名前:型:Layer]` で行う (core/parser.py)。
  - Change Summary (Before/After Viewの最小版, §14) は、選択中のtimestampに
    Eventがあれば、その直前(t-1)と直後(t)のWorldStateを比較して
    テキストで差分を示す。ノードを2枚並べるフル版のBefore/After Viewは
    今回のスコープ外 (README参照)。
---------------------------------------------------------------------------

--- Phase 4 追記 ---------------------------------------------------------
Worldbuilding Linter (§15) を接続する。
  - core/linter.py の lint() が、Parser issue / Patch conflict /
    Secondary Indexerのambiguity / WorldStateEngineに対する新規チェック
    (Temporal Contradiction, Relation Date Contradiction, Missing Reference)
    をひとつのリストに集約する。
  - 結果はLinterPanel (ui/linter_panel.py) にそのまま表示する。
    Linterはテキストやデータを一切書き換えない (読み取り専用の検証)。
  - 毎回の再パース(_reparse)のたびに自動的に再実行する。
---------------------------------------------------------------------------
"""

from __future__ import annotations

import re
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QWidget,
)

from core.events import Effect, new_event
from core.indexer import index_natural_lines
from core.linter import lint
from core.models import WorldModel
from core.parser import extract_relation_type, parse_codex_syntax
from core.world_state import WorldStateEngine
from ui.candidate_panel import CandidatePanel
from ui.graph_view import GraphView
from ui.linter_panel import LinterPanel
from ui.timeline_panel import AddEventDialog, TimelinePanel

GENERATED_SECTION_HEADING = "# Generated Relations"

SAMPLE_TEXT = """\
# Axral Codex - Sample

[A:Character]
[B:Organization]
[C:Character]

[A:Character] -> [B:Organization] : 所属
B -> C : 所属
A -> C : 尊敬

AはTear以前、Bの組織に所属していた。
しかしTearの後、AはBと対立するようになった。
CはAを裏切った。
"""

DEBOUNCE_MS = 250


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Axral Codex - MVP1 (Explicit Text -> Graph)")
        self.resize(1200, 760)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(SAMPLE_TEXT)
        self.editor.setStyleSheet("font-family: Menlo, Consolas, monospace; font-size: 13px;")

        self.graph_view = GraphView()
        self.graph_view.relation_type_edit_requested.connect(self._edit_relation_type)

        self.candidate_panel = CandidatePanel()
        self.candidate_panel.setMinimumWidth(320)
        self.candidate_panel.candidate_accepted.connect(self._accept_candidate)
        self.candidate_panel.candidate_ignored.connect(self._ignore_candidate)

        splitter = QSplitter()
        splitter.addWidget(self.editor)
        splitter.addWidget(self.graph_view)
        splitter.addWidget(self.candidate_panel)
        splitter.setSizes([440, 620, 320])
        self.setCentralWidget(splitter)

        self.timeline_panel = TimelinePanel()
        self.timeline_panel.timestamp_changed.connect(self._on_timeline_changed)
        self.timeline_panel.timeline_mode_toggled.connect(self._on_timeline_changed)
        self.timeline_panel.layer_filter_changed.connect(self._on_timeline_changed)
        self.timeline_panel.add_event_requested.connect(self._add_event)
        self.timeline_panel.event_removed.connect(self._remove_event)

        timeline_dock = QDockWidget("Timeline Lens (Phase 3, §14)", self)
        timeline_dock.setWidget(self.timeline_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, timeline_dock)

        self.linter_panel = LinterPanel()
        self.linter_panel.issue_activated.connect(self._jump_to_line)
        linter_dock = QDockWidget("Worldbuilding Linter (Phase 4, §15)", self)
        linter_dock.setWidget(self.linter_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, linter_dock)
        self.tabifyDockWidget(timeline_dock, linter_dock)
        timeline_dock.raise_()

        # World State Engine (Phase 0b実装済み)。Initial Stateは再パースのたびに
        # 最新のCanonical Dataへ同期する (_reparse内で set_initial_model)。
        self.world_engine = WorldStateEngine(WorldModel())

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._reparse)

        self.editor.textChanged.connect(self._debounce.start)

        # Ignoreされた候補のsignature集合。テキストが変わっても同一文・同一候補なら
        # 再表示しない (セッション内のみ有効。Canonical Dataや本文には触れない)。
        self._ignored_signatures: set[tuple] = set()
        # 直近のIndex結果を id -> Candidate で保持し、Accept時に参照する。
        self._candidates_by_id: dict[str, "object"] = {}
        # 直近のParseResult。Conflict解消時にrelationのsource_refs等を参照する。
        self._last_result = None

        self._build_menu()
        self._reparse()

    # ---- Menu -------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")

        open_action = file_menu.addAction("Open Codex Text...")
        open_action.triggered.connect(self._open_text)

        save_action = file_menu.addAction("Save Codex Text...")
        save_action.triggered.connect(self._save_text)

        file_menu.addSeparator()

        export_action = file_menu.addAction("Export Canonical Data (JSON)...")
        export_action.triggered.connect(self._export_json)

        patches_menu = self.menuBar().addMenu("Patches")
        resolve_action = patches_menu.addAction("Resolve Conflicts...")
        resolve_action.triggered.connect(self._resolve_conflicts)

    def _open_text(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Codex Text", "", "Text (*.txt *.md)")
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            self.editor.setPlainText(f.read())

    def _save_text(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Codex Text", "", "Text (*.txt *.md)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.editor.toPlainText())

    def _export_json(self) -> None:
        result = parse_codex_syntax(self.editor.toPlainText())
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Canonical Data", "world.json", "JSON (*.json)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(result.model.to_json())
        QMessageBox.information(self, "Export完了", f"Canonical Dataを書き出しました:\n{path}")

    # ---- Core loop ----------------------------------------------------

    def _reparse(self) -> None:
        """
        Primary Parser -> Canonical Data -> Graph View
        Primary Parser.natural_lines -> Secondary Indexer -> Candidate Panel
        という2系統のデータフロー (§4.4, §4.3) をそのまま実装したもの。
        """
        text = self.editor.toPlainText()
        result = parse_codex_syntax(text)
        self._last_result = result

        # World State EngineのInitial Stateを最新のCanonical Dataに同期する。
        # (Human-authored Textの編集が常にInitial Stateへ反映されるようにする)
        self.world_engine.set_initial_model(result.model)
        self.timeline_panel.set_events(self.world_engine.events_sorted())
        self._refresh_timestamp_range()

        self._render_graph()

        index_result = index_natural_lines(
            result.natural_lines, list(result.model.entities.values())
        )
        visible = [
            c
            for c in index_result.candidates
            if self._signature(c) not in self._ignored_signatures
        ]
        self._candidates_by_id = {c.id: c for c in visible}
        self.candidate_panel.set_candidates(visible)

        status_parts = [
            f"Entities: {len(result.model.entities)}",
            f"Relations: {len(result.model.relations)}",
            f"Candidates: {len(visible)}",
        ]
        if index_result.ambiguities:
            status_parts.append(f"⚠ Ambiguous lines: {len(index_result.ambiguities)}")
        if result.patch_conflicts:
            status_parts.append(
                f"⚠ Patch conflicts: {len(result.patch_conflicts)} "
                f"(Patches > Resolve Conflicts...)"
            )

        lint_issues = lint(result, self.world_engine, index_result)
        self.linter_panel.set_issues(lint_issues)
        if lint_issues:
            status_parts.append(f"Linter: {len(lint_issues)} issue(s)")

        self.status.showMessage("  ".join(status_parts))

    def _jump_to_line(self, line: int) -> None:
        """LinterPanelの項目をダブルクリックすると該当行にカーソルを移動する。"""
        block = self.editor.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        cursor = self.editor.textCursor()
        cursor.setPosition(block.position())
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    @staticmethod
    def _signature(candidate) -> tuple:
        """Ignore状態を再パース後も維持するためのキー。"""
        return (candidate.line, candidate.source_name, candidate.target_name, candidate.rel_type)

    # ---- Candidate confirmation (§4.3.1, §10.1) ------------------------

    def _accept_candidate(self, candidate_id: str) -> None:
        candidate = self._candidates_by_id.get(candidate_id)
        if candidate is None:
            return
        line = f"{candidate.source_name} -> {candidate.target_name} : {candidate.rel_type}"
        self._append_to_generated_section(line)
        # Ignoreと衝突しないよう、確定した候補のsignatureも今後の再表示対象から除く
        self._ignored_signatures.add(self._signature(candidate))
        self._debounce.start()

    def _ignore_candidate(self, candidate_id: str) -> None:
        candidate = self._candidates_by_id.get(candidate_id)
        if candidate is None:
            return
        self._ignored_signatures.add(self._signature(candidate))
        # テキストもCanonical Dataも変えないため、即座にパネルだけ更新すれば良い
        remaining = [c for c in self._candidates_by_id.values() if c.id != candidate_id]
        self._candidates_by_id = {c.id: c for c in remaining}
        self.candidate_panel.set_candidates(remaining)

    def _append_to_generated_section(self, codex_line: str) -> None:
        """
        「# Generated Relations」セクションへ確定Codex Syntax行を追記する。
        セクションが無ければ文末に新設する。Human-authored Textより上には
        絶対に挿入しない (§18.1 Never Destroy Human-authored Text)。
        """
        self._insert_into_generated_section([codex_line])

    def _insert_into_generated_section(self, block_lines: list[str]) -> None:
        """
        「# Generated Relations」セクション内に複数行のブロックを追記する
        (Patchブロックなど、複数行になるものはこちらを使う)。
        """
        text = self.editor.toPlainText()
        lines = text.splitlines()

        heading_idx = None
        for i, line in enumerate(lines):
            if line.strip() == GENERATED_SECTION_HEADING:
                heading_idx = i
                break

        if heading_idx is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(GENERATED_SECTION_HEADING)
            lines.append("")
            lines.extend(block_lines)
        else:
            insert_at = len(lines)
            for j in range(heading_idx + 1, len(lines)):
                if lines[j].strip().startswith("#"):
                    insert_at = j
                    break
            while insert_at > heading_idx + 1 and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines[insert_at:insert_at] = block_lines

        self.editor.setPlainText("\n".join(lines))

    # ---- Canvas -> Patch (§10.2, Phase 2) --------------------------------

    def _edit_relation_type(self, ref_key: str, old_type: str, new_type: str) -> None:
        """
        GraphView上でRelationラベルを編集した結果を受け取り、PATCHブロックとして
        書き込む。Original Textの該当行そのものは一切書き換えない。

        "was" にはGraphViewから渡されたold_type (Patch適用後の表示値かもしれない)
        ではなく、Original Textに実際に書かれている現在値を使う。そうしないと、
        同じRelationを2回連続で編集した際、2回目の"was"が「1回目のPatchで
        変化した後の値」になってしまい、Original Textとの比較が壊れる。
        """
        was = self._current_text_type(ref_key)
        if was is None:
            was = old_type
        self._upsert_patch_block(ref_key, field="type", value=new_type, was=was)
        self._debounce.start()

    def _current_text_type(self, ref_key: str) -> str | None:
        if self._last_result is None:
            return None
        relation = self._last_result.model.find_by_ref_key(ref_key)
        if relation is None or not relation.source_refs:
            return None
        return extract_relation_type(relation.source_refs[0].text)

    def _upsert_patch_block(self, ref_key: str, field: str, value: str, was: str) -> None:
        lines = self.editor.toPlainText().splitlines()
        start, end = self._find_patch_block_range(lines, ref_key)

        new_block = [f"PATCH {ref_key}:", f'  {field} = "{value}"  # was: "{was}"']

        if start is None:
            self._insert_into_generated_section(new_block)
            return

        lines[start:end] = new_block
        self.editor.setPlainText("\n".join(lines))

    def _remove_patch_block(self, ref_key: str) -> None:
        lines = self.editor.toPlainText().splitlines()
        start, end = self._find_patch_block_range(lines, ref_key)
        if start is None:
            return
        del lines[start:end]
        self.editor.setPlainText("\n".join(lines))

    @staticmethod
    def _find_patch_block_range(lines: list[str], ref_key: str) -> tuple:
        """
        "PATCH <ref_key>:" 見出し行と、それに続く "key = value" 形式の
        本文行の範囲 [start, end) を返す。見つからなければ (None, None)。
        """
        heading = f"PATCH {ref_key}:"
        for i, line in enumerate(lines):
            if line.strip() != heading:
                continue
            end = i + 1
            while end < len(lines) and re.match(
                r'^\s*[A-Za-z_]+\s*=\s*".*"', lines[end]
            ):
                end += 1
            return i, end
        return None, None

    # ---- Timeline Lens (Phase 3, §14) -------------------------------------

    def _render_graph(self) -> None:
        """
        TimelinePanelの状態 (Timeline mode / Layer filter) に応じて、
        「現在の(Live)WorldModel」か「WorldStateEngineの特定時点のWorldState」
        のどちらをGraphViewに渡すかを切り替える。
        """
        visible_layers = self.timeline_panel.visible_layers()
        if self.timeline_panel.is_timeline_mode():
            timestamp = self.timeline_panel.current_timestamp()
            state = self.world_engine.state_at(timestamp)
            self.graph_view.render_model(state, visible_layers=visible_layers)
            self.timeline_panel.set_change_summary(self._compute_change_summary(timestamp))
        else:
            model = self._last_result.model if self._last_result else WorldModel()
            self.graph_view.render_model(model, visible_layers=visible_layers)
            self.timeline_panel.set_change_summary("")

    def _on_timeline_changed(self, *_args) -> None:
        self._render_graph()

    def _refresh_timestamp_range(self) -> None:
        events = self.world_engine.events_sorted()
        if not events:
            self.timeline_panel.set_timestamp_range(-50, 50)
            return
        ts = [e.timestamp for e in events]
        margin = max(10, (max(ts) - min(ts)) // 4 or 10)
        self.timeline_panel.set_timestamp_range(min(ts) - margin, max(ts) + margin)

    def _compute_change_summary(self, timestamp: int) -> str:
        """Before/After Viewの最小版: t-1とtのWorldStateを比較して差分を文章化する。"""
        events_at_t = [e for e in self.world_engine.events_sorted() if e.timestamp == timestamp]
        if not events_at_t:
            return "(この時点で発生するEventはありません)"

        before = self.world_engine.state_at(timestamp - 1)
        after = self.world_engine.state_at(timestamp)
        lines: list[str] = []
        for event in events_at_t:
            lines.append(f"[{event.type}] t={event.timestamp}")
            for effect in event.effects:
                lines.append("  " + self._describe_effect(effect, before, after))
        return "\n".join(lines)

    @staticmethod
    def _describe_effect(effect: Effect, before, after) -> str:
        if effect.kind == "entity_existence":
            b = before.entities.get(effect.target_id)
            a = after.entities.get(effect.target_id)
            if a is None:
                return f"(不明なEntity: {effect.target_id})"
            b_val = b.existence if b else "?"
            return f"{a.name}.existence: {b_val} -> {a.existence}"
        if effect.kind == "relation_status":
            b = before.relations.get(effect.target_id)
            a = after.relations.get(effect.target_id)
            if a is None:
                return f"(不明なRelation: {effect.target_id})"
            b_val = b.status if b else "?"
            return f"{a.ref_key or a.id}.status: {b_val} -> {a.status}"
        if effect.kind == "relation_add":
            return f"+ new relation: {effect.payload}"
        if effect.kind == "relation_end":
            return f"relation ended: {effect.target_id}"
        if effect.kind == "entity_attribute":
            return f"attribute {effect.payload.get('key')} = {effect.payload.get('value')}"
        return f"(未対応のEffect kind: {effect.kind})"

    def _add_event(self) -> None:
        model = self._last_result.model if self._last_result else WorldModel()
        entity_names = [e.name for e in model.entities.values()]
        relation_refs = [r.ref_key for r in model.relations.values() if r.ref_key]

        dialog = AddEventDialog(entity_names, relation_refs, parent=self)
        if dialog.exec() != AddEventDialog.Accepted:
            return
        values = dialog.result_values()

        target_id = None
        if values["effect_kind"] == "entity_existence":
            entity = model.resolve(values["target"])
            target_id = entity.id if entity else None
        else:
            relation = model.find_by_ref_key(values["target"])
            target_id = relation.id if relation else None

        if target_id is None or not values["value"]:
            QMessageBox.warning(self, "Add Event", "対象または値が正しく指定されていません。")
            return

        payload_key = "existence" if values["effect_kind"] == "entity_existence" else "status"
        effect = Effect(kind=values["effect_kind"], target_id=target_id, payload={payload_key: values["value"]})
        event = new_event(
            timestamp=values["timestamp"],
            type_=values["type"],
            participants=[target_id],
            effects=[effect],
            is_snapshot_point=values["is_snapshot_point"],
        )
        self.world_engine.add_event(event)
        self.timeline_panel.set_events(self.world_engine.events_sorted())
        self._refresh_timestamp_range()
        self._render_graph()

    def _remove_event(self, event_id: str) -> None:
        self.world_engine.remove_event(event_id)
        self.timeline_panel.set_events(self.world_engine.events_sorted())
        self._refresh_timestamp_range()
        self._render_graph()

    # ---- Conflict Resolution (§11) ---------------------------------------

    def _resolve_conflicts(self) -> None:
        result = self._last_result
        if result is None or not result.patch_conflicts:
            QMessageBox.information(self, "Conflicts", "現在Conflictはありません。")
            return

        for conflict in list(result.patch_conflicts):
            self._resolve_one_conflict(conflict)
        self._debounce.start()

    def _resolve_one_conflict(self, conflict) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Conflict detected")
        box.setText(
            f"「{conflict.ref_key}」の {conflict.field} でConflictが発生しています。\n\n"
            f"Original (現在の本文): {conflict.text_value}\n"
            f"Generated Patch:      {conflict.patch_value}\n"
            f"Patch作成時点のOriginal: {conflict.expected_was}"
        )
        keep_btn = box.addButton("Keep Text", QMessageBox.AcceptRole)
        apply_btn = box.addButton("Apply Canvas Change", QMessageBox.AcceptRole)
        merge_btn = box.addButton("Merge", QMessageBox.AcceptRole)
        diff_btn = box.addButton("Open Diff", QMessageBox.ActionRole)
        box.addButton("Skip", QMessageBox.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked is keep_btn:
            self._remove_patch_block(conflict.ref_key)
        elif clicked is apply_btn:
            self._apply_canvas_change(conflict)
        elif clicked is merge_btn:
            self._merge_conflict(conflict)
        elif clicked is diff_btn:
            QMessageBox.information(
                self,
                "Diff",
                f"- Original: {conflict.text_value}\n+ Patch:    {conflict.patch_value}",
            )
            self._resolve_one_conflict(conflict)  # Diffを見た後、改めて選択させる
        # Skip: 何もしない (次回再パース時にも同じConflictとして残る)

    def _apply_canvas_change(self, conflict) -> None:
        """[Apply Canvas Change]: PatchのほうをOriginal Textへそのまま反映する。"""
        if self._write_value_to_original(conflict, conflict.patch_value):
            self._remove_patch_block(conflict.ref_key)

    def _merge_conflict(self, conflict) -> None:
        """
        [Merge] (§11.3): OriginalとPatch、どちらか一方を機械的に採用するのではなく、
        ユーザーが両者を見比べたうえで最終的な値を自分で決められるようにする。

        今回のConflictは単一フィールド(type等)の値の食い違いであり、複数行テキストの
        マージのような「部分的に両方を取り込む」操作は意味を持たない
        (2つの文字列の一部ずつを継ぎ合わせても大抵は無意味な値になる)。そのため、
        ここでのMergeは「両方の値を提示したうえで、ユーザーが最終値を入力する」
        という形にする — 単純な二択(Keep Text / Apply Canvas Change)では
        「PatchでもOriginalでもない、第三の正しい値」を選べないケースに対応する。
        """
        merged_value, ok = QInputDialog.getText(
            self,
            "Merge",
            f"「{conflict.ref_key}」の {conflict.field} を統合します。\n\n"
            f"Original: {conflict.text_value}\n"
            f"Patch:    {conflict.patch_value}\n\n"
            f"最終的に採用する値を入力してください:",
            text=conflict.patch_value,
        )
        if not ok:
            return
        merged_value = merged_value.strip()
        if not merged_value:
            QMessageBox.warning(self, "Merge", "空の値は適用できません。")
            return
        if self._write_value_to_original(conflict, merged_value):
            self._remove_patch_block(conflict.ref_key)

    def _write_value_to_original(self, conflict, value: str) -> bool:
        """
        Original Textの該当行 (§18.1 で保護されているHuman-authored Text) に
        指定した値を直接書き込む。[Apply Canvas Change] と [Merge] の両方が使う
        共通処理。書き込みに成功したかどうかを返す。
        """
        model = self._last_result.model if self._last_result else None
        relation = model.find_by_ref_key(conflict.ref_key) if model else None
        if relation is None or not relation.source_refs:
            QMessageBox.warning(self, "Conflicts", "対象のRelationが見つかりませんでした。")
            return False

        target_line_no = relation.source_refs[0].line
        lines = self.editor.toPlainText().splitlines()
        idx = target_line_no - 1
        if not (0 <= idx < len(lines)):
            return False

        updated, n = re.subn(
            r":\s*" + re.escape(conflict.text_value) + r"\s*$",
            f": {value}",
            lines[idx],
        )
        if n == 0:
            QMessageBox.warning(
                self, "Conflicts", "本文の該当箇所を特定できませんでした (手動で編集してください)。"
            )
            return False

        lines[idx] = updated
        self.editor.setPlainText("\n".join(lines))
        return True


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
