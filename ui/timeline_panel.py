"""
Axral Codex - Timeline Panel (Phase 3: Timeline Lens §14)

plan.md (v2) §13, §14 に対応するUI。

対応スコープ:
  - Timelineスクラバー: 任意timestampを選び、core/world_state.py の
    WorldStateEngine.state_at() を呼ぶためのUI操作を提供する
    (Engine自体はPhase 0bで実装済み)。
  - Layer Slider (§13): LAYER_HIERARCHYの各Layerを表示/非表示切り替え。
    実際のフィルタリングはGraphView側 (render_modelのvisible_layers引数) で行う。
  - Event追加/削除の簡易UI (Add Event Dialog)。
  - Change Summary: 選択中のtimestampで発生するEventの変化を
    「before -> after」のテキストで表示する (Before/After Viewの最小版)。
    ノードを2枚並べて描画するフル版のBefore/After ViewはPhase 3の残タスク。

このモジュールはWorldStateEngineや現在のEntity/Relation一覧を直接知らない。
必要な情報 (Entity名リスト・Relation ref_keyリスト・Event一覧・変化サマリ文字列)
はすべてmain.py側から渡す設計にし、Panel自身はCanonical Dataに触れない。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.events import Event
from core.models import LAYER_HIERARCHY


class AddEventDialog(QDialog):
    """
    Eventを1件追加するための最小限のダイアログ。
    Effectは1つだけ (entity_existence または relation_status) をこの場で作れる。
    それ以上複雑なEvent編集 (複数Effect・relation_add等) は将来のUI拡張とする。
    """

    def __init__(self, entity_names: list[str], relation_refs: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Event を追加")
        layout = QFormLayout(self)

        self.timestamp_spin = QSpinBox()
        self.timestamp_spin.setRange(-100000, 100000)
        layout.addRow("Timestamp:", self.timestamp_spin)

        self.type_edit = QLineEdit("Event")
        self.type_edit.setPlaceholderText("例: Tear, Chapter, MajorEvent, 自由入力も可")
        layout.addRow("Type:", self.type_edit)

        self.snapshot_check = QCheckBox("Snapshot Point にする (§9.1.1)")
        layout.addRow(self.snapshot_check)

        self.effect_kind_combo = QComboBox()
        self.effect_kind_combo.addItems(["entity_existence", "relation_status"])
        layout.addRow("Effect kind:", self.effect_kind_combo)

        self.target_combo = QComboBox()
        layout.addRow("対象:", self.target_combo)

        self.value_edit = QLineEdit()
        layout.addRow("新しい値:", self.value_edit)

        self._entity_names = entity_names
        self._relation_refs = relation_refs
        self.effect_kind_combo.currentTextChanged.connect(self._refresh_targets)
        self._refresh_targets(self.effect_kind_combo.currentText())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _refresh_targets(self, kind: str) -> None:
        self.target_combo.clear()
        if kind == "entity_existence":
            self.target_combo.addItems(self._entity_names)
            self.value_edit.setPlaceholderText("例: dead / confirmed")
        else:
            self.target_combo.addItems(self._relation_refs)
            self.value_edit.setPlaceholderText("confirmed / hypothetical / rumor")

    def result_values(self) -> dict:
        return {
            "timestamp": self.timestamp_spin.value(),
            "type": self.type_edit.text().strip() or "Event",
            "is_snapshot_point": self.snapshot_check.isChecked(),
            "effect_kind": self.effect_kind_combo.currentText(),
            "target": self.target_combo.currentText(),
            "value": self.value_edit.text().strip(),
        }


class TimelinePanel(QWidget):
    timestamp_changed = Signal(int)
    timeline_mode_toggled = Signal(bool)
    layer_filter_changed = Signal(set)
    event_removed = Signal(str)  # event_id
    add_event_requested = Signal()  # main.pyがダイアログを開いてEventを組み立てる

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.mode_check = QCheckBox("Timeline State を表示する (Phase 3)")
        self.mode_check.toggled.connect(self.timeline_mode_toggled)
        layout.addWidget(self.mode_check)

        slider_row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(-100, 100)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.timestamp_label = QLabel("t = 0")
        self.timestamp_label.setMinimumWidth(60)
        slider_row.addWidget(self.slider)
        slider_row.addWidget(self.timestamp_label)
        layout.addLayout(slider_row)

        layout.addWidget(QLabel("Change Summary (Before → After, §14):"))
        self.change_summary = QTextEdit()
        self.change_summary.setReadOnly(True)
        self.change_summary.setMaximumHeight(90)
        self.change_summary.setPlaceholderText(
            "この時点で発生するEventの変化がここに表示されます"
        )
        layout.addWidget(self.change_summary)

        layer_box = QGroupBox("Layer Slider (§13)")
        layer_layout = QHBoxLayout(layer_box)
        self._layer_checks: dict[str, QCheckBox] = {}
        for layer_name in LAYER_HIERARCHY:
            cb = QCheckBox(layer_name)
            cb.setChecked(True)
            cb.toggled.connect(self._on_layer_toggled)
            layer_layout.addWidget(cb)
            self._layer_checks[layer_name] = cb
        layout.addWidget(layer_box)

        events_box = QGroupBox("Events")
        events_layout = QVBoxLayout(events_box)
        self.event_list = QListWidget()
        events_layout.addWidget(self.event_list)
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add Event...")
        self.delete_btn = QPushButton("Delete Selected")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.delete_btn)
        events_layout.addLayout(btn_row)
        layout.addWidget(events_box)

        self.add_btn.clicked.connect(self.add_event_requested)
        self.delete_btn.clicked.connect(self._on_delete_clicked)

    def _on_slider_changed(self, value: int) -> None:
        self.timestamp_label.setText(f"t = {value}")
        self.timestamp_changed.emit(value)

    def _on_layer_toggled(self, _checked: bool) -> None:
        visible = {name for name, cb in self._layer_checks.items() if cb.isChecked()}
        self.layer_filter_changed.emit(visible)

    def _on_delete_clicked(self) -> None:
        item = self.event_list.currentItem()
        if item is None:
            return
        self.event_removed.emit(item.data(Qt.UserRole))

    def set_events(self, events: list[Event]) -> None:
        self.event_list.clear()
        for e in sorted(events, key=lambda e: (e.timestamp, e.id)):
            marker = " ★snapshot" if e.triggers_snapshot else ""
            item = QListWidgetItem(f"t={e.timestamp}  [{e.type}]{marker}")
            item.setData(Qt.UserRole, e.id)
            self.event_list.addItem(item)

    def set_timestamp_range(self, minimum: int, maximum: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setRange(minimum, maximum)
        self.slider.blockSignals(False)

    def set_change_summary(self, text: str) -> None:
        self.change_summary.setPlainText(text)

    def is_timeline_mode(self) -> bool:
        return self.mode_check.isChecked()

    def current_timestamp(self) -> int:
        return self.slider.value()

    def visible_layers(self) -> set[str]:
        return {name for name, cb in self._layer_checks.items() if cb.isChecked()}
