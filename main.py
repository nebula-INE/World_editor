"""
Axral Codex - MVP1 "Explicit Text -> Graph" (plan.md v2 準拠)

対応スコープ:
  - Phase 0a: Entity / Relation の最小Canonical Data Model (core/models.py)
  - Phase 1 : Codex Syntaxの決定論的Primary Parser (core/parser.py)
  - Phase 1 : Live Preview (§4.6) — 入力から即座にGraphへ反映
  - Phase 2 : Graph Canvasの最小描画 (ui/graph_view.py, 編集機能はまだ無し)

意図的にスコープ外にしているもの (plan.mdの原則に従い、後続Phaseへ):
  - Secondary / Background Indexer (自然言語からのCandidate抽出, Phase 1.5)
  - Non-destructive Text Sync / Patch / Conflict UI (Phase 2本編)
  - Timeline / Layer / World State / Snapshot (Phase 3, MVP4)
  - Linter (Phase 4)

Background Processing (§4.4) の原則に対応し、Primary Parserは
QTimerによる短いデバウンス後にのみ実行する。パース自体はまだ軽量な
正規表現ベースなのでUIスレッドで十分間に合うが、Secondary Indexerを
追加する際はここをQThread/Workerへ切り出す前提の構成にしてある。
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

from core.parser import parse_codex_syntax
from ui.graph_view import GraphView

SAMPLE_TEXT = """\
# Axral Codex - Sample

[A:Character]
[B:Organization]
[C:Character]

[A:Character] -> [B:Organization] : 所属
B -> C : 所属
A -> C : 尊敬
A -> B : 対立
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

        splitter = QSplitter()
        splitter.addWidget(self.editor)
        splitter.addWidget(self.graph_view)
        splitter.setSizes([480, 720])
        self.setCentralWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self._reparse)

        self.editor.textChanged.connect(self._debounce.start)

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
        Primary Parser -> Canonical Data -> Graph View という
        plan.md §4.4 のデータフローそのままの実装。
        """
        text = self.editor.toPlainText()
        result = parse_codex_syntax(text)
        self.graph_view.render_model(result.model)
        self.status.showMessage(
            f"Entities: {len(result.model.entities)}  "
            f"Relations: {len(result.model.relations)}"
        )


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
