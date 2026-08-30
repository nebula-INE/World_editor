"""
Axral Codex - Linter Panel (Phase 4, §15)

core/linter.py が生成した LintIssue のリストを表示するだけのシンプルなView。
重大度(warning/info)でアイコンを出し分ける。クリックした行がテキスト上の
どこにあるか分かるよう、対象行番号を併記する (source_refs同様の考え方)。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from core.linter import LintIssue, Severity

_SEVERITY_ICON = {
    Severity.WARNING: "⚠",
    Severity.INFO: "ℹ",
}


class LinterPanel(QWidget):
    issue_activated = Signal(int)  # line number (該当行へジャンプしたい場合に使う)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

    def set_issues(self, issues: list[LintIssue]) -> None:
        self.list_widget.clear()
        if not issues:
            item = QListWidgetItem("問題は見つかりませんでした ✓")
            self.list_widget.addItem(item)
            return

        for issue in issues:
            icon = _SEVERITY_ICON.get(issue.severity, "•")
            line_part = f"  (line {issue.line})" if issue.line else ""
            text = f"{icon} [{issue.code}] {issue.message}{line_part}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, issue.line)
            self.list_widget.addItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        line = item.data(Qt.UserRole)
        if line:
            self.issue_activated.emit(line)
