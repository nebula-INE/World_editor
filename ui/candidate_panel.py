"""
Axral Codex - Candidate Panel (Phase 1.5: Inline Suggestions / User Confirmation)

plan.md (v2) §4.3.1 の "Candidate -> User Review -> Confirmed Relation" を
UIとして実装したもの。Accept/Ignoreのどちらも、Canonical Dataを直接書き換える
のではなく "Generated Relations" セクションへ確定Codex Syntaxを追記する形で行う
(§10.1 Generated Section の考え方をそのまま踏襲。Non-destructive Text Syncの
本格的なPatch機構はPhase 2で実装するため、MVP1.5では最小構成としてこの形をとる)。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.indexer import Candidate

_LEVEL_COLOR = {
    "high": "#3B9E56",
    "medium": "#C9962C",
    "low": "#B04A4A",
}


class CandidateRow(QFrame):
    accepted = Signal(str)  # candidate.id
    ignored = Signal(str)  # candidate.id

    def __init__(self, candidate: Candidate, parent=None) -> None:
        super().__init__(parent)
        self.candidate = candidate
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #2B2E33; border-radius: 6px; margin: 3px; }"
            "QLabel { color: #EAEAEA; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        headline = QLabel(
            f"<b>{candidate.source_name}</b> ── {candidate.rel_type} ──▶ "
            f"<b>{candidate.target_name}</b>"
        )
        layout.addWidget(headline)

        color = _LEVEL_COLOR.get(candidate.confidence_level, "#999999")
        meta = QLabel(
            f'<span style="color:{color}">● {candidate.confidence_level.upper()} '
            f"({candidate.confidence:.2f})</span> &nbsp; "
            f'<span style="color:#9AA0A6">line {candidate.line}</span>'
            + (
                ' &nbsp; <span style="color:#D08A3E">⚠ ambiguous</span>'
                if candidate.ambiguous
                else ""
            )
        )
        layout.addWidget(meta)

        source_label = QLabel(f'<span style="color:#9AA0A6">「{candidate.source_text}」</span>')
        source_label.setWordWrap(True)
        layout.addWidget(source_label)

        btn_row = QHBoxLayout()
        accept_btn = QPushButton("Accept")
        accept_btn.setStyleSheet("QPushButton { background:#3B9E56; color:white; padding:4px 10px; }")
        accept_btn.clicked.connect(lambda: self.accepted.emit(self.candidate.id))

        ignore_btn = QPushButton("Ignore")
        ignore_btn.setStyleSheet("QPushButton { background:#4A4E55; color:white; padding:4px 10px; }")
        ignore_btn.clicked.connect(lambda: self.ignored.emit(self.candidate.id))

        btn_row.addWidget(accept_btn)
        btn_row.addWidget(ignore_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)


class CandidatePanel(QScrollArea):
    """Candidate一覧を表示し、Accept/Ignoreをシグナルで上位に伝える。"""

    candidate_accepted = Signal(str)
    candidate_ignored = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.addStretch()
        self.setWidget(self._container)
        self._empty_label = QLabel(
            "候補はありません。\n自然文を書くとここに候補が表示されます。"
        )
        self._empty_label.setStyleSheet("color:#888; padding: 12px;")

    def set_candidates(self, candidates: list[Candidate]) -> None:
        # 既存の行をクリア
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not candidates:
            self._layout.addWidget(self._empty_label)
            self._layout.addStretch()
            return

        # confidence降順で表示（自信のある候補を上に）
        for candidate in sorted(candidates, key=lambda c: c.confidence, reverse=True):
            row = CandidateRow(candidate)
            row.accepted.connect(self.candidate_accepted)
            row.ignored.connect(self.candidate_ignored)
            self._layout.addWidget(row)
        self._layout.addStretch()
