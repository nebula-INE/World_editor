"""
Axral Codex - Graph View (Phase 2 "Graph Canvas")

plan.md (v2) 対応スコープ:
  - Node / Edge Rendering, Auto Layout (初期配置のみ), Graph Editing
  - Relation.status (§7.1) に応じた線種の出し分け
    (confirmed=実線 / hypothetical=破線 / rumor=点線)
  - Canvas → Data: ノードのRelationラベルをダブルクリックで編集すると、
    `relation_type_edit_requested` シグナルを発行する。GraphView自身は
    Canonical Dataやテキストを一切書き換えない — 実際にPatchとして
    Generated Sectionへ書き込むのは呼び出し側 (main.py) の責務にする
    (§10.1/§10.2 Non-destructive Text Syncの原則: Canvasは提案するだけ)。

意図的にスコープ外にしていること:
  - Infinite Canvas (現状は通常のQGraphicsView。ズーム/パンはできるが
    無限スクロール最適化やViewport Cullingは Phase 5)
  - Entity属性の編集 (今回はRelation.typeの編集のみ。plan.md §10.2の
    Patch例もrelation.typeを対象にしている)
  - Undo/Redo
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QInputDialog,
)

from core.models import Relation, WorldModel

NODE_RADIUS = 34
LAYER_COLORS = {
    "Character": QColor("#5B8DEF"),
    "Organization": QColor("#E0A73C"),
    "Location": QColor("#5FB878"),
    "Unknown": QColor("#9AA0A6"),
}


def _pen_for_status(status: str) -> QPen:
    """Relation.status (§7.1) に対応する線種。confirmed/hypothetical/rumor。"""
    pen = QPen(QColor("#444444"))
    pen.setWidthF(2.0)
    if status == "hypothetical":
        pen.setStyle(Qt.DashLine)
    elif status == "rumor":
        pen.setStyle(Qt.DotLine)
    else:
        pen.setStyle(Qt.SolidLine)
    return pen


class NodeItem(QGraphicsEllipseItem):
    """
    ドラッグ移動可能なノード。原点(0,0)を中心とした円で定義し、
    setPos()でシーン上の位置を管理する(pos() = ノード中心のシーン座標)。
    """

    def __init__(self, entity_id: str, on_move) -> None:
        super().__init__(-NODE_RADIUS, -NODE_RADIUS, NODE_RADIUS * 2, NODE_RADIUS * 2)
        self.entity_id = entity_id
        self.edges: list["EdgeItem"] = []
        self._on_move = on_move
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)
        self.setCursor(Qt.OpenHandCursor)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_path()
            if self._on_move:
                self._on_move(self.entity_id, self.pos())
        return super().itemChange(change, value)


class EdgeLabelItem(QGraphicsSimpleTextItem):
    """
    Relationラベル。ダブルクリックすると GraphView に編集をリクエストする
    (§10.2 Patch-style Sync の起点。Canonical Dataはここでは変更しない)。
    """

    def __init__(self, text: str, edge: "EdgeItem", graph_view: "GraphView") -> None:
        super().__init__(text)
        self._edge = edge
        self._view = graph_view
        self.setZValue(3)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._view.request_relation_edit(self._edge)
        event.accept()


class EdgeItem:
    """線・矢頭・ラベルをまとめて管理する非Item補助クラス。"""

    def __init__(
        self,
        scene: QGraphicsScene,
        source_node: NodeItem,
        target_node: NodeItem,
        relation: Relation,
        graph_view: "GraphView",
    ) -> None:
        self.source_node = source_node
        self.target_node = target_node
        self.relation = relation

        self.path_item = QGraphicsPathItem()
        self.path_item.setZValue(0)
        scene.addItem(self.path_item)

        self.arrow_item = QGraphicsPathItem()
        self.arrow_item.setPen(QPen(Qt.NoPen))
        self.arrow_item.setBrush(QBrush(QColor("#444444")))
        self.arrow_item.setZValue(0)
        scene.addItem(self.arrow_item)

        self.label_item = EdgeLabelItem(relation.type, self, graph_view)
        self.label_item.setBrush(QBrush(QColor("#222222")))
        scene.addItem(self.label_item)

        source_node.edges.append(self)
        target_node.edges.append(self)
        self.update_path()

    def update_path(self) -> None:
        p1 = self.source_node.pos()
        p2 = self.target_node.pos()
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(dx, dy)

        if length > 0:
            ux, uy = dx / length, dy / length
            start = QPointF(p1.x() + ux * NODE_RADIUS, p1.y() + uy * NODE_RADIUS)
            end = QPointF(p2.x() - ux * NODE_RADIUS, p2.y() - uy * NODE_RADIUS)
        else:
            start, end = p1, p2

        path = QPainterPath(start)
        path.lineTo(end)
        self.path_item.setPath(path)
        self.path_item.setPen(_pen_for_status(self.relation.status))

        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_size = 10
        p_a = end - QPointF(
            math.cos(angle - math.pi / 7) * arrow_size,
            math.sin(angle - math.pi / 7) * arrow_size,
        )
        p_b = end - QPointF(
            math.cos(angle + math.pi / 7) * arrow_size,
            math.sin(angle + math.pi / 7) * arrow_size,
        )
        arrow_path = QPainterPath(end)
        arrow_path.lineTo(p_a)
        arrow_path.lineTo(p_b)
        arrow_path.closeSubpath()
        self.arrow_item.setPath(arrow_path)

        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        rect = self.label_item.boundingRect()
        self.label_item.setPos(mid.x() - rect.width() / 2, mid.y() - rect.height() / 2)
        self.label_item.setText(self.relation.type)


class GraphView(QGraphicsView):
    """
    WorldModelを受け取って描画するView。
    ノードはドラッグで動かせ、位置はEntity単位で(再描画をまたいで)保持する。
    Relationラベルのダブルクリックは `relation_type_edit_requested` を発行する。
    """

    relation_type_edit_requested = Signal(str, str, str)  # ref_key, old_type, new_type

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)

        self._node_items: dict[str, NodeItem] = {}
        # Entity単位のドラッグ位置。再描画(render_model)をまたいで保持する。
        self._positions: dict[str, QPointF] = {}
        self._has_fit = False

    def render_model(self, model, visible_layers: set[str] | None = None) -> None:
        """
        model は WorldModel または WorldState (entities/relations dictを持つ
        任意のオブジェクト) を受け付ける。Phase 3のTimeline Lensで
        WorldStateEngine.state_at() の結果をそのまま渡せるようにするため。

        visible_layers (Phase 3, §13 Layer Slider):
          Noneなら全Layerを表示。集合が渡された場合、entity.layerが
          その集合に含まれないEntityは非表示にする。ただしlayer未設定
          (None) のEntityは「未分類」として常に表示する。
        """
        self._scene.clear()
        self._node_items = {}

        all_entities = list(model.entities.values())
        if visible_layers is None:
            entities = all_entities
        else:
            entities = [e for e in all_entities if e.layer is None or e.layer in visible_layers]

        if not entities:
            self._scene.addText("（Codex Syntaxを入力するとここに世界が図になります）")
            self._has_fit = False
            return

        # 新規Entityのみ円周配置。既存Entityはドラッグした位置を維持する。
        n = len(entities)
        radius = max(160, 60 * n)
        cx, cy = radius + 80, radius + 80
        for i, entity in enumerate(entities):
            if entity.id not in self._positions:
                angle = 2 * math.pi * i / n
                self._positions[entity.id] = QPointF(
                    cx + radius * math.cos(angle), cy + radius * math.sin(angle)
                )

        for entity in entities:
            node = NodeItem(entity.id, on_move=self._remember_position)
            node.setBrush(QBrush(LAYER_COLORS.get(entity.type, LAYER_COLORS["Unknown"])))
            node.setPen(QPen(QColor("#222222"), 1.5))
            node.setPos(self._positions[entity.id])
            self._scene.addItem(node)
            self._add_node_labels(node, entity.name, entity.type)
            self._node_items[entity.id] = node

        visible_ids = {e.id for e in entities}
        for relation in model.relations.values():
            if relation.source not in visible_ids or relation.target not in visible_ids:
                continue
            src = self._node_items.get(relation.source)
            tgt = self._node_items.get(relation.target)
            if src is None or tgt is None:
                continue
            EdgeItem(self._scene, src, tgt, relation, self)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        if not self._has_fit:
            # 初回描画時だけ全体表示にフィットさせる。以降はユーザーのズーム/パン/
            # ドラッグ操作を再描画のたびにリセットしないよう、fitInViewは呼ばない。
            self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
            self._has_fit = True

    def _remember_position(self, entity_id: str, pos: QPointF) -> None:
        self._positions[entity_id] = QPointF(pos)

    def _add_node_labels(self, node: NodeItem, name: str, type_: str) -> None:
        # ノードの子アイテムにする — 親がsetPos()で動くと自動的に追従する
        label = QGraphicsSimpleTextItem(name, node)
        label.setBrush(QBrush(QColor("#FFFFFF")))
        rect = label.boundingRect()
        label.setPos(-rect.width() / 2, -rect.height() / 2 - 8)
        label.setZValue(2)

        type_label = QGraphicsSimpleTextItem(type_, node)
        type_label.setBrush(QBrush(QColor("#F0F0F0")))
        trect = type_label.boundingRect()
        type_label.setPos(-trect.width() / 2, 6)
        type_label.setZValue(2)

    # ---- Canvas -> Patch (§10.2) --------------------------------------------

    def request_relation_edit(self, edge: EdgeItem) -> None:
        """
        ラベルダブルクリックで呼ばれる。ここではダイアログで新しい値を聞くだけで、
        Canonical Data / Textへの書き込みは一切行わない。実際の書き込みは
        `relation_type_edit_requested` を受け取った側 (main.py) がPatchとして行う。
        """
        relation = edge.relation
        new_type, ok = QInputDialog.getText(
            self,
            "Relationを編集",
            f"{relation.ref_key} の関係タイプ:",
            text=relation.type,
        )
        if not ok:
            return
        new_type = new_type.strip()
        if not new_type or new_type == relation.type:
            return
        self.relation_type_edit_requested.emit(relation.ref_key, relation.type, new_type)
