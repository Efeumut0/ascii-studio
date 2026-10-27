from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QTableWidget, QWidget


class WindowSurface(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 0 if self.window().isMaximized() else 12
        if radius == 0:
            painter.fillRect(self.rect(), QColor("#242628"))
        painter.setPen(QPen(QColor("#454646"), 1))
        painter.setBrush(QColor("#242628"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


class VideoTable(QTableWidget):
    def __init__(self, rows=0, columns=3, parent=None):
        super().__init__(rows, columns, parent)
        self.hovered_row = -1
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def update_hover(self, position=None):
        row = self.indexAt(position).row() if position is not None and self.isEnabled() else -1
        if row != self.hovered_row:
            self.hovered_row = row
            self.viewport().update()

    def viewportEvent(self, event):
        if event.type() in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
            self.update_hover(event.position().toPoint())
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self.update_hover()
        return super().viewportEvent(event)

    def scrollContentsBy(self, horizontal, vertical):
        super().scrollContentsBy(horizontal, vertical)
        position = self.viewport().mapFromGlobal(QCursor.pos())
        self.update_hover(position if self.viewport().rect().contains(position) else None)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.EnabledChange and not self.isEnabled():
            self.update_hover()
        super().changeEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.isEnabled() and 0 <= self.hovered_row < self.rowCount():
            rectangle = self.visualRect(self.model().index(self.hovered_row, 0))
            outline = QRectF(2, rectangle.top() + 2, self.viewport().width() - 5, rectangle.height() - 4)
            painter.setPen(QPen(QColor("#c1a17f"), 1))
            painter.drawRoundedRect(outline, 6, 6)
        if self.selectionModel().hasSelection():
            row = self.currentRow()
            rectangle = self.visualRect(self.model().index(row, 0))
            painter.setPen(QPen(QColor("#d4aa7e"), 2))
            painter.drawLine(1, rectangle.top() + 7, 1, rectangle.bottom() - 7)
