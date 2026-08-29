"""
Axral Codex - MVP1 "Explicit Text -> Graph" (plan.md v2 準拠)

対応スコープ:
  - Phase 0a: Entity / Relation の最小Canonical Data Model (core/models.py)
  - Phase 1 : Codex Syntaxの決定論的Primary Parser (core/parser.py)
  - Phase 1 : Live Preview (§4.6) — 入力から即座にGraphへ反映
  - Phase 1.5: Secondary Indexer (自然言語→Candidate, core/indexer.py) と
               Inline Suggestions / User Confirmation UI (ui/candidate_panel.py)
  - Phase 2 : Graph Canvasの最小描画 (ui/graph_view.py, 編集機能はまだ無し)

意図的にスコープ外にしているもの (plan.mdの原則に従い、後続Phaseへ):
  - Embedding Signal / LLM Signal によるConfidence算出 (§4.5.1、Phase 1.5後半)
  - Non-destructive Text Sync本編 / Patch / Conflict UI (Phase 2本編。
    ここではGenerated Sectionへの単純追記のみ実装)
  - Timeline / Layer / World State / Snapshot (Phase 3, MVP4)
  - Linter (Phase 4)

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
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QWidget,
)

from core.indexer import index_natural_lines
from core.parser import parse_codex_syntax
from ui.candidate_panel import CandidatePanel
from ui.graph_view import GraphView

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
        self.graph_view.render_model(result.model)

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
        self.status.showMessage("  ".join(status_parts))

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
            lines.append(codex_line)
        else:
            # セクション内の最後（次の見出しの手前 or 文末）に追記する
            insert_at = len(lines)
            for j in range(heading_idx + 1, len(lines)):
                if lines[j].strip().startswith("#"):
                    insert_at = j
                    break
            while insert_at > heading_idx + 1 and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines.insert(insert_at, codex_line)

        self.editor.setPlainText("\n".join(lines))


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
