"""
Axral Codex - Graph View (Phase 2 "Graph Canvas" の最小実装)

plan.md (v2)ではPhase 2でInfinite Canvas / Auto Layout / Editingを
本格実装する予定だが、MVP1のGoalは「明示的に書いた構造が確実に図になる」
ことの検証であるため、ここでは:
  - 円周上への単純な自動配置 (Auto Layoutの最小版)
  - ノード/エッジの読み取り専用描画
  - Relation.status (§7.1) に応じた線種の出し分け
    (confirmed=実線 / hypothetical=破線 / rumor=点線, §7.1のCanvas表現に対応)
のみを提供する。Canvas編集・Non-destructive Text Sync (Phase 2本編) は
このMVP1版のスコープ外。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from core.models import WorldModel

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


class GraphView(QGraphicsView):
    """WorldModelを受け取り、円周レイアウトで再描画するだけのシンプルなView。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

    def render_model(self, model: WorldModel) -> None:
        self._scene.clear()
        entities = list(model.entities.values())
        if not entities:
            self._scene.addText("（Codex Syntaxを入力するとここに世界が図になります）")
            return

        positions: dict[str, QPointF] = {}
        n = len(entities)
        radius = max(160, 60 * n)
        cx, cy = radius + 80, radius + 80
        for i, entity in enumerate(entities):
            angle = 2 * math.pi * i / n
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            positions[entity.id] = QPointF(x, y)

        # Relationを先に描く（ノードの下に線が来るように）
        for relation in model.relations.values():
            if relation.source not in positions or relation.target not in positions:
                continue
            p1 = positions[relation.source]
            p2 = positions[relation.target]
            self._draw_edge(p1, p2, relation.type, relation.status)

        for entity in entities:
            self._draw_node(positions[entity.id], entity.name, entity.type)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    def _draw_node(self, pos: QPointF, name: str, type_: str) -> None:
        color = LAYER_COLORS.get(type_, LAYER_COLORS["Unknown"])
        ellipse = QGraphicsEllipseItem(
            pos.x() - NODE_RADIUS, pos.y() - NODE_RADIUS, NODE_RADIUS * 2, NODE_RADIUS * 2
        )
        ellipse.setBrush(QBrush(color))
        ellipse.setPen(QPen(QColor("#222222"), 1.5))
        ellipse.setZValue(1)
        self._scene.addItem(ellipse)

        label = QGraphicsSimpleTextItem(name)
        label.setBrush(QBrush(QColor("#FFFFFF")))
        rect = label.boundingRect()
        label.setPos(pos.x() - rect.width() / 2, pos.y() - rect.height() / 2 - 8)
        label.setZValue(2)
        self._scene.addItem(label)

        type_label = QGraphicsSimpleTextItem(type_)
        type_label.setBrush(QBrush(QColor("#F0F0F0")))
        trect = type_label.boundingRect()
        type_label.setPos(pos.x() - trect.width() / 2, pos.y() + 6)
        type_label.setZValue(2)
        self._scene.addItem(type_label)

    def _draw_edge(self, p1: QPointF, p2: QPointF, rel_type: str, status: str) -> None:
        line = QLineF(p1, p2)
        # ノード円の外周からエッジを始める（円の中心から生やさない）
        if line.length() > 0:
            unit = QPointF(line.dx() / line.length(), line.dy() / line.length())
            start = QPointF(p1.x() + unit.x() * NODE_RADIUS, p1.y() + unit.y() * NODE_RADIUS)
            end = QPointF(p2.x() - unit.x() * NODE_RADIUS, p2.y() - unit.y() * NODE_RADIUS)
        else:
            start, end = p1, p2

        path = QPainterPath(start)
        path.lineTo(end)
        path_item = QGraphicsPathItem(path)
        path_item.setPen(_pen_for_status(status))
        path_item.setZValue(0)
        self._scene.addItem(path_item)

        # 矢頭
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
        arrow_item = QGraphicsPathItem(arrow_path)
        arrow_item.setBrush(QBrush(QColor("#444444")))
        arrow_item.setPen(QPen(Qt.NoPen))
        arrow_item.setZValue(0)
        self._scene.addItem(arrow_item)

        # ラベル
        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        label = QGraphicsSimpleTextItem(rel_type)
        label.setBrush(QBrush(QColor("#222222")))
        rect = label.boundingRect()
        label.setPos(mid.x() - rect.width() / 2, mid.y() - rect.height() / 2)
        label.setZValue(3)
        self._scene.addItem(label)
