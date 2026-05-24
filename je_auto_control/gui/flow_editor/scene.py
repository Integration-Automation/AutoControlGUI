"""Qt scene that paints a :func:`layout_steps` output as a node graph."""
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsSimpleTextItem, QStyleOptionGraphicsItem, QWidget,
)

from je_auto_control.gui.flow_editor.layout import (
    FlowEdge, FlowLayout, FlowNodePosition, NODE_HEIGHT, NODE_WIDTH,
    layout_steps,
)
from je_auto_control.gui.script_builder.step_model import Step


_NODE_BG = QColor(60, 70, 85)
_NODE_BG_SELECTED = QColor(95, 120, 160)
_NODE_BORDER = QColor(200, 210, 220)
_NODE_LABEL = QColor(240, 240, 240)
_EDGE_PEN = QColor(200, 200, 200)


class FlowNodeItem(QGraphicsRectItem):
    """One painted command rectangle. Stores the originating step path."""

    def __init__(self, position: FlowNodePosition,
                 on_clicked: Callable[[Tuple], None]) -> None:
        super().__init__(QRectF(position.x, position.y,
                                  position.width, position.height))
        self._path = position.path
        self._on_clicked = on_clicked
        self._set_default_brush()
        self.setPen(QPen(_NODE_BORDER, 1.5))
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._build_label(position)

    @property
    def step_path(self) -> Tuple:
        return self._path

    def _set_default_brush(self) -> None:
        self.setBrush(QBrush(_NODE_BG))

    def _build_label(self, position: FlowNodePosition) -> None:
        command = QGraphicsSimpleTextItem(position.command, self)
        command.setBrush(QBrush(_NODE_LABEL))
        font = QFont()
        font.setBold(True)
        command.setFont(font)
        command.setPos(position.x + 8, position.y + 8)

        # Strip the command prefix from the label to avoid duplication.
        label = position.label
        if label.startswith(position.command):
            label = label[len(position.command):].strip()
        if label:
            detail = QGraphicsSimpleTextItem(label, self)
            detail.setBrush(QBrush(_NODE_LABEL))
            detail.setPos(position.x + 8, position.y + 32)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        try:
            self._on_clicked(self._path)
        except (RuntimeError, OSError):
            pass

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem,
              widget: Optional[QWidget] = None) -> None:
        if self.isSelected():
            self.setBrush(QBrush(_NODE_BG_SELECTED))
        else:
            self._set_default_brush()
        super().paint(painter, option, widget)


class FlowEdgeItem(QGraphicsPathItem):
    """Curved arrow between two FlowNodeItems."""

    def __init__(self, edge: FlowEdge, source: FlowNodeItem,
                 target: FlowNodeItem) -> None:
        super().__init__()
        self._edge = edge
        path = QPainterPath()
        sx = source.rect().right()
        sy = source.rect().center().y()
        tx = target.rect().left()
        ty = target.rect().center().y()
        path.moveTo(sx, sy)
        mid_x = (sx + tx) / 2
        path.cubicTo(mid_x, sy, mid_x, ty, tx, ty)
        self.setPath(path)
        pen = QPen(_EDGE_PEN, 1.5)
        self.setPen(pen)
        if edge.body_key:
            mid = (mid_x, (sy + ty) / 2 - 8)
            label = QGraphicsSimpleTextItem(edge.body_key, self)
            label.setBrush(QBrush(_EDGE_PEN))
            label.setPos(*mid)


class FlowGraphScene(QGraphicsScene):
    """Owns one ``FlowNodeItem`` per step plus all the connecting edges."""

    node_selected = Signal(tuple)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(QColor(30, 35, 45)))
        self._nodes: Dict[Tuple, FlowNodeItem] = {}

    def load(self, steps: List[Step]) -> FlowLayout:
        """Replace the scene with a freshly-laid-out ``steps`` tree."""
        self.clear()
        self._nodes.clear()
        layout = layout_steps(steps)
        for position in layout.nodes:
            item = FlowNodeItem(position, self._emit_selected)
            self.addItem(item)
            self._nodes[position.path] = item
        for edge in layout.edges:
            source = self._nodes.get(edge.source)
            target = self._nodes.get(edge.target)
            if source is None or target is None:
                continue
            self.addItem(FlowEdgeItem(edge, source, target))
        if layout.nodes:
            self.setSceneRect(
                -20.0, -20.0,
                layout.width + 40.0, layout.height + 40.0,
            )
        else:
            self.setSceneRect(-20.0, -20.0,
                               NODE_WIDTH + 40.0, NODE_HEIGHT + 40.0)
        return layout

    def _emit_selected(self, path: Tuple) -> None:
        self.node_selected.emit(path)

    def node_paths(self) -> List[Tuple]:
        return list(self._nodes.keys())


__all__ = ["FlowEdgeItem", "FlowGraphScene", "FlowNodeItem"]
