"""Reusable help, progressive disclosure and future viewer interface."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QLabel, QToolButton, QVBoxLayout, QWidget, QHBoxLayout,
)


class HelpButton(QToolButton):
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.setText("?")
        self.setAccessibleName(f"Help: {title}")
        self.setToolTip(text)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.popover = QFrame(self, Qt.WindowType.ToolTip)
        layout = QVBoxLayout(self.popover)
        label = QLabel(f"{title}\n\n{text}")
        label.setWordWrap(True)
        label.setMaximumWidth(340)
        layout.addWidget(label)
        self.clicked.connect(self.show_help)

    def show_help(self):
        self.popover.move(self.mapToGlobal(self.rect().bottomLeft()))
        self.popover.show()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.show_help()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.popover.hide()


class AdvancedPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toggle = QToolButton()
        self.toggle.setText("Advanced")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.content = QWidget()
        body = QHBoxLayout(self.content)
        label = QLabel("Specialist simulation controls will be connected here.")
        label.setWordWrap(True)
        body.addWidget(label)
        body.addWidget(HelpButton("Advanced controls", "Sampling, slice thickness and aberrations affect accuracy and cost. These controls are not active in this initial demo."))
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self.set_expanded)
        self.set_expanded(False)

    def set_expanded(self, expanded):
        self.toggle.setChecked(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)


class ViewerPlaceholder(QFrame):
    """Replace with VisPy/ASE adapter; no orientation calculations here.

    The adapter must publish its exact canonical 3x3 view matrix and hand that
    same matrix to the science adapter. Displayed angles are never a source.
    """
    orientation_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("viewer")
        self.setMinimumSize(350, 300)
        layout = QVBoxLayout(self)
        title = QLabel("2  Orient specimen")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.caption = QLabel("3D viewport\n\nVisPy / ASE viewer integration pending\nVisual orientation is unavailable in this scaffold.")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption, 1)
        layout.addWidget(HelpButton("Specimen orientation", "The final viewer and simulation must use the same exact view matrix. No orientation or physics is calculated in this demo."))

    def set_specimen_summary(self, name):
        self.caption.setText(f"{name}\n\n3D viewer integration pending\nVisual orientation is unavailable in this scaffold.")
