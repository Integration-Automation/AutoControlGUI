"""Tree view of script steps with nested bodies for flow-control commands."""
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.gui.script_builder.step_model import Step


ROLE_STEP = Qt.ItemDataRole.UserRole + 1
ROLE_BODY_KEY = Qt.ItemDataRole.UserRole + 2


class StepTreeView(QTreeWidget):
    """Tree of steps.

    Each top-level item is a Step. Items whose command has ``body_keys`` get
    one child per body key; the body-key items host the nested Step children.
    """

    selected_step_changed = Signal(object)  # emits Optional[Step]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Step"])
        self.setColumnCount(1)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._roots: List[Step] = []
        self.itemSelectionChanged.connect(self._emit_selection)

    def load_steps(self, steps: List[Step]) -> None:
        """Rebuild the tree from a list of root Steps."""
        self.clear()
        self._roots = list(steps)
        for step in self._roots:
            self.addTopLevelItem(_build_item(step))
        self.expandAll()

    def root_steps(self) -> List[Step]:
        """Return the current root Step list (kept in sync via refresh)."""
        return list(self._roots)

    def refresh_current_label(self) -> None:
        """Update the label of the currently selected item after edits."""
        item = self.currentItem()
        if item is None:
            return
        step = item.data(0, ROLE_STEP)
        if isinstance(step, Step):
            item.setText(0, step.label)

    def add_step(self, step: Step) -> None:
        """Append a new Step at the most appropriate location."""
        parent_item, body_key = self._selected_body_target()
        if parent_item is None or body_key is None:
            self._roots.append(step)
            self.addTopLevelItem(_build_item(step))
            return
        parent_step: Step = parent_item.data(0, ROLE_STEP)
        parent_step.bodies.setdefault(body_key, []).append(step)
        body_item = _find_body_item(parent_item, body_key)
        if body_item is None:
            body_item = _add_body_node(parent_item, body_key)
        body_item.addChild(_build_item(step))
        body_item.setExpanded(True)

    def remove_selected(self) -> None:
        """Remove the currently selected Step (not body-key nodes)."""
        item = self.currentItem()
        if item is None or item.data(0, ROLE_STEP) is None:
            return
        step = item.data(0, ROLE_STEP)
        parent = item.parent()
        if parent is None:
            self._roots.remove(step)
            index = self.indexOfTopLevelItem(item)
            self.takeTopLevelItem(index)
            return
        body_key = parent.data(0, ROLE_BODY_KEY)
        grandparent_step: Step = parent.parent().data(0, ROLE_STEP)
        siblings = grandparent_step.bodies.get(body_key, [])
        if step in siblings:
            siblings.remove(step)
        parent.removeChild(item)

    def move_selected(self, offset: int) -> None:
        """Shift the selected Step up (offset=-1) or down (+1) in its list."""
        item = self.currentItem()
        if item is None or item.data(0, ROLE_STEP) is None:
            return
        parent = item.parent()
        siblings = self._sibling_list(parent)
        if siblings is None:
            return
        step = item.data(0, ROLE_STEP)
        idx = siblings.index(step)
        new_idx = idx + offset
        if not 0 <= new_idx < len(siblings):
            return
        siblings[idx], siblings[new_idx] = siblings[new_idx], siblings[idx]
        if parent is None:
            self.takeTopLevelItem(self.indexOfTopLevelItem(item))
            self.insertTopLevelItem(new_idx, item)
        else:
            parent.removeChild(item)
            parent.insertChild(new_idx, item)
        self.setCurrentItem(item)

    def _sibling_list(self, parent_item: Optional[QTreeWidgetItem]
                      ) -> Optional[List[Step]]:
        if parent_item is None:
            return self._roots
        body_key = parent_item.data(0, ROLE_BODY_KEY)
        if body_key is None:
            return None
        grandparent = parent_item.parent()
        if grandparent is None:
            return None
        grandparent_step: Step = grandparent.data(0, ROLE_STEP)
        return grandparent_step.bodies.setdefault(body_key, [])

    def _selected_body_target(self) -> Tuple[Optional[QTreeWidgetItem], Optional[str]]:
        item = self.currentItem()
        if item is None:
            return None, None
        body_key = item.data(0, ROLE_BODY_KEY)
        if body_key is not None:
            return item.parent(), body_key
        step = item.data(0, ROLE_STEP)
        if isinstance(step, Step) and step.bodies:
            first_key = next(iter(step.bodies))
            return item, first_key
        return None, None

    def _emit_selection(self) -> None:
        item = self.currentItem()
        step = item.data(0, ROLE_STEP) if item is not None else None
        self.selected_step_changed.emit(step if isinstance(step, Step) else None)


def _build_item(step: Step) -> QTreeWidgetItem:
    item = QTreeWidgetItem([step.label])
    item.setData(0, ROLE_STEP, step)
    spec = COMMAND_SPECS.get(step.command)
    if spec is not None:
        for body_key in spec.body_keys:
            body_item = _add_body_node(item, body_key)
            for child_step in step.bodies.get(body_key, []):
                body_item.addChild(_build_item(child_step))
    return item


def _add_body_node(parent: QTreeWidgetItem, body_key: str) -> QTreeWidgetItem:
    node = QTreeWidgetItem([f"[{body_key}]"])
    node.setData(0, ROLE_BODY_KEY, body_key)
    node.setFlags(node.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
    parent.addChild(node)
    return node


def _find_body_item(parent: QTreeWidgetItem, body_key: str) -> Optional[QTreeWidgetItem]:
    for i in range(parent.childCount()):
        child = parent.child(i)
        if child.data(0, ROLE_BODY_KEY) == body_key:
            return child
    return None
