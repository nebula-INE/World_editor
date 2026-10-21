"""Standalone Axral Story authoring dialog; independent from world-project persistence."""
from __future__ import annotations
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)
from core.story import BLOCK_TYPES, WORK_KINDS, parse_story, serialize_story
from core.story_editing import (
    add_chapter, rename_chapter, reorder_chapter, delete_chapter,
    add_scene, rename_scene, reorder_scene, delete_scene,
    add_block, update_block, reorder_block, delete_block,
)
from core.story_file import load_story_file, save_story_file, STORY_FILE_SUFFIX

KIND_LABELS = {
    "novel": "小説", "screenplay": "脚本", "audio_drama": "音声ドラマ",
    "game_scenario": "ゲームシナリオ", "trpg_scenario": "TRPGシナリオ",
    "storyboard": "絵コンテ",
}
BLOCK_LABELS = {"prose": "地の文", "dialogue": "台詞", "narration": "ナレーション", "direction": "演出指示", "note": "メモ"}

def _id() -> str:
    return uuid.uuid4().hex

def _story_filename(title: str) -> str:
    """Build a cross-platform-safe default filename for a standalone story."""
    cleaned = "".join(
        "_" if char in '<>:"/\\|?*' or ord(char) < 32 else char
        for char in title.strip()
    )
    cleaned = cleaned.rstrip(". ")[:100].rstrip(". ")
    return (cleaned or "untitled") + STORY_FILE_SUFFIX


def _empty_story() -> dict[str, Any]:
    return {"format": "axral-story", "schema_version": 1, "work_id": _id(),
            "title": "無題の物語", "kind": "novel", "chapters": []}

class StoryAuthoringDialog(QDialog):
    """Edits only standalone .axral-story.json files."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Axral Story Authoring")
        self.resize(1080, 720)
        self.story = _empty_story()
        self._dirty = False
        self._saved_snapshot = serialize_story(self.story)
        self.current_chapter_id: str | None = None
        self.current_scene_id: str | None = None
        self._loading = False
        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.title_edit = QLineEdit(self.story["title"])
        self.kind_combo = QComboBox()
        for key in sorted(WORK_KINDS):
            self.kind_combo.addItem(KIND_LABELS[key], key)
        toolbar.addWidget(QLabel("作品タイトル"))
        toolbar.addWidget(self.title_edit, 1)
        toolbar.addWidget(QLabel("種別"))
        toolbar.addWidget(self.kind_combo)
        root.addLayout(toolbar)
        filebar = QHBoxLayout()
        for label, callback in (("新規", self.new_story), ("開く", self.open_story), ("保存", self.save_story)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            filebar.addWidget(button)
        filebar.addStretch(1)
        close = QPushButton("閉じる")
        close.clicked.connect(self.close)
        filebar.addWidget(close)
        root.addLayout(filebar)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget(); left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("章"))
        self.chapters = QListWidget(); left_layout.addWidget(self.chapters)
        self.chapter_title = QLineEdit(); self.chapter_title.setPlaceholderText("章タイトル"); left_layout.addWidget(self.chapter_title)
        row = QHBoxLayout()
        for label, cb in (("＋章", self.add_chapter), ("↑", lambda: self.move_chapter(-1)), ("↓", lambda: self.move_chapter(1)), ("削除", self.remove_chapter)):
            b=QPushButton(label); b.clicked.connect(cb); row.addWidget(b)
        left_layout.addLayout(row)
        splitter.addWidget(left)

        middle = QWidget(); middle_layout = QVBoxLayout(middle)
        middle_layout.addWidget(QLabel("シーン"))
        self.scenes = QListWidget(); middle_layout.addWidget(self.scenes)
        row = QHBoxLayout()
        for label, cb in (("＋シーン", self.add_scene), ("↑", lambda: self.move_scene(-1)), ("↓", lambda: self.move_scene(1)), ("削除", self.remove_scene)):
            b=QPushButton(label); b.clicked.connect(cb); row.addWidget(b)
        middle_layout.addLayout(row)
        splitter.addWidget(middle)

        right = QWidget(); right_layout = QVBoxLayout(right)
        self.scene_title = QLineEdit(); self.scene_title.setPlaceholderText("シーン名")
        right_layout.addWidget(self.scene_title)
        blockbar = QHBoxLayout()
        self.block_type = QComboBox()
        for key in sorted(BLOCK_TYPES):
            self.block_type.addItem(BLOCK_LABELS[key], key)
        blockbar.addWidget(self.block_type, 1)
        add_block_button = QPushButton("＋本文ブロック"); add_block_button.clicked.connect(self.add_text_block)
        blockbar.addWidget(add_block_button)
        right_layout.addLayout(blockbar)
        self.blocks = QListWidget(); right_layout.addWidget(self.blocks, 1)
        row = QHBoxLayout()
        for label, cb in (("↑", lambda: self.move_block(-1)), ("↓", lambda: self.move_block(1)), ("削除", self.remove_block)):
            b=QPushButton(label); b.clicked.connect(cb); row.addWidget(b)
        row.addStretch(1); row.addWidget(QLabel("選択ブロック本文"))
        right_layout.addLayout(row)
        self.body = QPlainTextEdit(); self.body.setPlaceholderText("本文を入力…")
        right_layout.addWidget(self.body, 3)
        self.speaker = QLineEdit(); self.speaker.setPlaceholderText("話者ID（台詞の場合・任意）")
        right_layout.addWidget(self.speaker)
        splitter.addWidget(right); splitter.setStretchFactor(2, 1)
        root.addWidget(splitter, 1)
        self.status = QLabel("独立した .axral-story.json として保存します。")
        root.addWidget(self.status)

        self.title_edit.textChanged.connect(self._title_changed)
        self.chapter_title.textChanged.connect(self._chapter_title_changed)
        self.kind_combo.currentIndexChanged.connect(self._kind_changed)
        self.chapters.currentRowChanged.connect(self._chapter_selected)
        self.scenes.currentRowChanged.connect(self._scene_selected)
        self.blocks.currentRowChanged.connect(self._block_selected)
        self.scene_title.textChanged.connect(self._scene_title_changed)
        self.body.textChanged.connect(self._body_changed)
        self.block_type.currentIndexChanged.connect(self._block_type_changed)
        self.speaker.textChanged.connect(self._speaker_changed)
        self._refresh_chapters()

    def _set_status(self, text: str) -> None:
        self.status.setText(text + (" · 未保存の変更あり" if self._dirty else ""))
    def _mark_dirty(self) -> None:
        try:
            self._dirty = serialize_story(self.story) != self._saved_snapshot
        except (TypeError, ValueError):
            self._dirty = True
        self._set_status("未保存の変更があります。" if self._dirty else "変更は保存済みです。")
    def _confirm_discard(self, action: str) -> bool:
        if not self._dirty:
            return True
        return QMessageBox.question(self, "未保存の変更", f"保存していない変更があります。{action}すると変更は失われます。続行しますか？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
    def closeEvent(self, event) -> None:
        if self._confirm_discard("閉じる"):
            event.accept()
        else:
            event.ignore()
    def _chapter(self) -> dict[str, Any] | None:
        return next((c for c in self.story["chapters"] if c["id"] == self.current_chapter_id), None)
    def _scene(self) -> dict[str, Any] | None:
        c=self._chapter()
        return next((s for s in c["scenes"] if s["id"] == self.current_scene_id), None) if c else None
    def _block(self) -> dict[str, Any] | None:
        s=self._scene(); row=self.blocks.currentRow()
        return s["blocks"][row] if s and 0 <= row < len(s["blocks"]) else None
    def _refresh_chapters(self, select_id: str | None = None) -> None:
        self._loading=True; self.chapters.clear()
        for c in self.story["chapters"]: self.chapters.addItem(c["title"])
        idx=next((i for i,c in enumerate(self.story["chapters"]) if c["id"] == (select_id or self.current_chapter_id)),-1)
        self.chapters.setCurrentRow(idx)
        selected = self.story["chapters"][idx] if idx >= 0 else None
        self.chapter_title.setText(selected["title"] if selected else "")
        self.chapter_title.setEnabled(selected is not None)
        self._loading=False
        if idx < 0:
            self.current_chapter_id=None
        self._refresh_scenes()
    def _refresh_scenes(self, select_id: str | None = None) -> None:
        self._loading=True; self.scenes.clear(); c=self._chapter()
        if c:
            for s in c["scenes"]: self.scenes.addItem(s["title"])
            idx=next((i for i,s in enumerate(c["scenes"]) if s["id"] == (select_id or self.current_scene_id)),-1)
        else: idx=-1
        self.scenes.setCurrentRow(idx); self._loading=False
        if idx < 0: self.current_scene_id=None
        self._refresh_blocks()
    def _refresh_blocks(self, select_row: int = -1) -> None:
        self._loading=True; self.blocks.clear(); s=self._scene()
        if s:
            for b in s["blocks"]: self.blocks.addItem(f'{b["order"]+1}. {BLOCK_LABELS[b["type"]]}')
            self.blocks.setCurrentRow(select_row if select_row >= 0 else (0 if s["blocks"] else -1))
        else: self.blocks.setCurrentRow(-1)
        self._loading=False; self._load_block_fields()
    def _load_block_fields(self) -> None:
        self._loading=True; b=self._block()
        self.body.setPlainText(b["text"] if b else "")
        self.speaker.setText(b.get("character_id") or "" if b else "")
        idx=self.block_type.findData(b["type"]) if b else 0
        self.block_type.setCurrentIndex(max(idx,0))
        self.body.setEnabled(b is not None); self.block_type.setEnabled(b is not None); self.speaker.setEnabled(b is not None)
        self.speaker.setVisible(bool(b and b["type"] == "dialogue"))
        s=self._scene(); self.scene_title.setText(s["title"] if s else ""); self.scene_title.setEnabled(s is not None)
        self._loading=False
    def _title_changed(self, value: str) -> None:
        if not self._loading:
            self.story["title"]=value; self._mark_dirty()
    def _kind_changed(self, _index: int) -> None:
        if not self._loading:
            self.story["kind"]=self.kind_combo.currentData(); self._mark_dirty()
    def _chapter_selected(self, row: int) -> None:
        if self._loading:return
        c=self.story["chapters"]; self.current_chapter_id=c[row]["id"] if 0<=row<len(c) else None
        chapter = c[row] if 0<=row<len(c) else None
        self.current_scene_id = chapter["scenes"][0]["id"] if chapter and chapter["scenes"] else None
        self._refresh_scenes(self.current_scene_id)
    def _scene_selected(self, row: int) -> None:
        if self._loading:return
        c=self._chapter(); scenes=c["scenes"] if c else []
        self.current_scene_id=scenes[row]["id"] if 0<=row<len(scenes) else None
        self._refresh_blocks()
    def _block_selected(self, _row: int) -> None:
        if not self._loading:self._load_block_fields()
    def _chapter_title_changed(self, value: str) -> None:
        if self._loading or not self.current_chapter_id:return
        self.story=rename_chapter(self.story,self.current_chapter_id,value); self._mark_dirty()
        row=next((i for i,c in enumerate(self.story["chapters"]) if c["id"]==self.current_chapter_id),-1)
        if row>=0:
            self._loading=True; self.chapters.item(row).setText(value); self._loading=False
    def _scene_title_changed(self, value: str) -> None:
        if self._loading or not self.current_scene_id:return
        self.story=rename_scene(self.story,self.current_scene_id,value); self._mark_dirty()
        c=self._chapter()
        if c:
            self._loading=True; row=next((i for i,s in enumerate(c["scenes"]) if s["id"]==self.current_scene_id),-1)
            if row>=0:self.scenes.item(row).setText(value)
            self._loading=False
    def _body_changed(self) -> None:
        if self._loading:return
        b=self._block()
        if b:
            try:self.story=update_block(self.story,b["id"],{"text":self.body.toPlainText()}); self._mark_dirty()
            except ValueError as exc:self._set_status(str(exc))
    def _block_type_changed(self, _index: int) -> None:
        if self._loading:return
        b=self._block()
        if b:
            self.story=update_block(self.story,b["id"],{"type":self.block_type.currentData()}); self._mark_dirty()
            self._refresh_blocks(self.blocks.currentRow())
    def _speaker_changed(self, value: str) -> None:
        if self._loading:return
        b=self._block()
        if b and b["type"]=="dialogue":
            self.story=update_block(self.story,b["id"],{"character_id":value or None}); self._mark_dirty()
    def add_chapter(self) -> None:
        title=f'第{len(self.story["chapters"])+1}章'; ident=_id()
        self.story=add_chapter(self.story,ident,title); self._mark_dirty(); self.current_chapter_id=ident; self.current_scene_id=None; self._refresh_chapters(ident); self._set_status("章を追加しました。")
    def remove_chapter(self) -> None:
        c=self._chapter()
        if not c:return
        if QMessageBox.question(self,"章を削除","この章と配下のシーン・本文を削除しますか？") != QMessageBox.Yes:return
        self.story=delete_chapter(self.story,c["id"]); self._mark_dirty(); self.current_chapter_id=self.story["chapters"][0]["id"] if self.story["chapters"] else None; self.current_scene_id=self.story["chapters"][0]["scenes"][0]["id"] if self.story["chapters"] and self.story["chapters"][0]["scenes"] else None; self._refresh_chapters(self.current_chapter_id); self._set_status("章を削除しました。")
    def move_chapter(self, delta: int) -> None:
        c=self._chapter()
        if not c:return
        to=c["order"]+delta
        if 0<=to<len(self.story["chapters"]): self.story=reorder_chapter(self.story,c["id"],to); self._mark_dirty(); self._refresh_chapters(c["id"])
    def add_scene(self) -> None:
        c=self._chapter()
        if not c:return
        ident=_id(); self.story=add_scene(self.story,c["id"],ident,f'シーン {len(c["scenes"])+1}'); self._mark_dirty(); self.current_scene_id=ident; self._refresh_scenes(ident); self._set_status("シーンを追加しました。")
    def remove_scene(self) -> None:
        s=self._scene()
        if not s:return
        if QMessageBox.question(self,"シーンを削除","このシーンの本文を削除しますか？") != QMessageBox.Yes:return
        self.story=delete_scene(self.story,s["id"]); self._mark_dirty(); c=self._chapter(); self.current_scene_id=c["scenes"][0]["id"] if c and c["scenes"] else None; self._refresh_scenes(self.current_scene_id); self._set_status("シーンを削除しました。")
    def move_scene(self, delta: int) -> None:
        s=self._scene()
        if not s:return
        to=s["order"]+delta
        if 0<=to<len(self._chapter()["scenes"]): self.story=reorder_scene(self.story,s["id"],to); self._mark_dirty(); self._refresh_scenes(s["id"])
    def add_text_block(self) -> None:
        s=self._scene()
        if not s:return
        ident=_id(); self.story=add_block(self.story,s["id"],{"id":ident,"type":"prose","text":""}); self._mark_dirty(); self._refresh_blocks(len(s["blocks"])); self._set_status("本文ブロックを追加しました。")
    def remove_block(self) -> None:
        b=self._block()
        if not b:return
        self.story=delete_block(self.story,b["id"]); self._mark_dirty(); self._refresh_blocks(min(self.blocks.currentRow(),len(self._scene()["blocks"])-1)); self._set_status("本文ブロックを削除しました。")
    def move_block(self, delta: int) -> None:
        b=self._block(); s=self._scene()
        if not b or not s:return
        to=b["order"]+delta
        if 0<=to<len(s["blocks"]): self.story=reorder_block(self.story,b["id"],to); self._mark_dirty(); self._refresh_blocks(to)
    def new_story(self) -> None:
        if not self._confirm_discard("新規作成"): return
        self.story=_empty_story(); self._saved_snapshot=serialize_story(self.story); self._dirty=False; self.current_chapter_id=None; self.current_scene_id=None
        self._loading=True; self.title_edit.setText(self.story["title"]); self.kind_combo.setCurrentIndex(self.kind_combo.findData("novel")); self._loading=False
        self._refresh_chapters(); self._set_status("新しい物語です。")
    def open_story(self) -> None:
        if not self._confirm_discard("別の物語を開く"): return
        path,_=QFileDialog.getOpenFileName(self,"物語ファイルを開く","","Axral Story (*"+STORY_FILE_SUFFIX+")")
        if not path:return
        try:
            self.story=load_story_file(path); self._saved_snapshot=serialize_story(self.story); self._dirty=False; first_chapter = next((chapter for chapter in self.story["chapters"] if chapter["scenes"]), None)
            selected_chapter = first_chapter or (self.story["chapters"][0] if self.story["chapters"] else None)
            self.current_chapter_id=selected_chapter["id"] if selected_chapter else None
            self.current_scene_id=selected_chapter["scenes"][0]["id"] if selected_chapter and selected_chapter["scenes"] else None; self._loading=True; self.title_edit.setText(self.story["title"]); self.kind_combo.setCurrentIndex(self.kind_combo.findData(self.story["kind"])); self._loading=False
            self._refresh_chapters(self.current_chapter_id); self._set_status(f"読み込みました: {Path(path).name}")
        except (ValueError,OSError) as exc: QMessageBox.warning(self,"物語ファイルを開けません",str(exc))
    def save_story(self) -> None:
        path,_=QFileDialog.getSaveFileName(self,"物語ファイルを保存",_story_filename(self.story["title"]),"Axral Story (*"+STORY_FILE_SUFFIX+")")
        if not path:return
        if not path.lower().endswith(STORY_FILE_SUFFIX):path+=STORY_FILE_SUFFIX
        try:
            save_story_file(path,parse_story(self.story)); self._saved_snapshot=serialize_story(self.story); self._dirty=False; self._set_status(f"保存しました: {Path(path).name}")
        except (ValueError,OSError) as exc: QMessageBox.warning(self,"物語ファイルを保存できません",str(exc))
