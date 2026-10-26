"""Her to-do list as a little yellow sticky note that sits beside the cat and follows her.

Type in the box at the bottom and press Enter to add a task, click a task to tick it off,
right-click it to delete it, and tuck the note away with the – button (the paw menu brings it
back).
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QWidget

from . import style
from .resources import settings

OPEN_KEY = "todoNoteOpen"
WIDTH = 240
PAD = 16
#: How far the note tucks behind the cat's (mostly transparent) window.
OVERLAP = 12
ROW = 28


class TodoNote(QWidget):
    def __init__(self, todos):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)   # (macOS hides tool windows otherwise)
        self.list = todos
        self.cat = None
        self.on_toggle = None      # (item, done)
        self.on_add = None         # (item)
        self.on_open_change = None
        self._rows: list[tuple[QRectF, dict]] = []
        self._tuck = QRectF()
        self._separator_y = 0
        self._field_box = QRectF()
        self._paws_y = None

        self.field = QLineEdit(self)
        self.field.setPlaceholderText("+ Add a task")
        self.field.setFrame(False)
        self.field.setFont(style.font(13, QFont.Weight.DemiBold))
        self.field.setStyleSheet(f"QLineEdit {{ background: transparent; color: {style.INK.name()}; }}")
        self.field.returnPressed.connect(self._add_from_field)
        self.field.installEventFilter(self)
        self.list.on_change = self.rebuild
        self.setMouseTracking(True)
        self.rebuild()

    @property
    def is_open(self) -> bool:
        return bool(settings.get(OPEN_KEY, True))

    def attach(self, cat):
        self.cat = cat
        if self.is_open:
            self._show()

    def set_open(self, open_: bool):
        settings.set(OPEN_KEY, open_)
        self._show() if open_ else self.hide()
        if self.on_open_change:
            self.on_open_change()

    def _show(self):
        if self.cat is None:
            return
        self.place()
        self.show()
        self.cat.raise_()   # the note sits just behind her

    def place(self):
        """On her left if there's room, otherwise on her right, bottoms lined up with her feet."""
        if self.cat is None:
            return
        cat = self.cat.frameGeometry()
        x = cat.left() - self.width() + OVERLAP
        y = cat.bottom() + 1 - self.height()
        screen = (self.cat.screen() or self.screen()).availableGeometry()
        if x < screen.left():
            x = cat.right() + 1 - OVERLAP
        x = min(max(x, screen.left()), screen.right() + 1 - self.width())
        y = min(max(y, screen.top()), screen.bottom() + 1 - self.height())
        if self.pos().x() != x or self.pos().y() != y:
            self.move(x, y)

    # MARK: - Editing

    def _add_from_field(self):
        text = self.field.text()
        if not text.strip():
            return
        if self.list.add(text):
            self.field.clear()
            if self.on_add:
                self.on_add(self.list.items[-1])
        else:
            QApplication.beep()   # the note is full

    def eventFilter(self, obj, event):
        # Escape stops typing without adding anything.
        if obj is self.field and event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.field.clear()
            self.field.clearFocus()
            return True
        return super().eventFilter(obj, event)

    def _toggle(self, item):
        done = self.list.toggle(item["id"])
        if done is not None and self.on_toggle:
            self.on_toggle(item, done)

    # MARK: - Layout

    def rebuild(self):
        inner = WIDTH - style.SHADOW - PAD * 2
        y = style.TAPE_OVERHANG + 14
        self._title_y = y
        self._tuck = QRectF(PAD + inner - 24, y, 24, 24)
        y += 24 + 8
        self._hint_y = y if not self.list.items else None
        if not self.list.items:
            y += 24
        self._rows = []
        for item in self.list.items:
            self._rows.append((QRectF(PAD, y, inner, ROW), item))
            y += ROW
        y += 8
        self._separator_y = y
        y += 10
        self._paws_y = y if self.list.items else None
        if self.list.items:
            y += 20 + 10
        self._field_box = QRectF(PAD, y, inner, 30)
        self.field.setGeometry(PAD + 8, round(y + 4), inner - 16, 22)
        y += 30 + PAD
        height = round(y + style.SHADOW)
        # Grow or shrink from the bottom edge, which lines up with the cat's feet.
        self.resize(WIDTH, height)
        self.place()
        self.update()

    # MARK: - Mouse

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        if self._tuck.contains(pos):
            self.set_open(False)
            return
        for rect, item in self._rows:
            if rect.contains(pos):
                self._toggle(item)
                return

    def contextMenuEvent(self, event):
        for rect, item in self._rows:
            if rect.contains(QPointF(event.pos())):
                menu = QMenu(self)
                text = item["text"] if len(item["text"]) <= 40 else item["text"][:39] + "…"
                menu.addAction(f'Delete "{text}"', lambda i=item: self.list.remove(i["id"]))
                menu.exec(event.globalPos())
                return

    def mouseMoveEvent(self, event):
        pos = event.position()
        clickable = self._tuck.contains(pos) or any(r.contains(pos) for r, _ in self._rows)
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        for rect, item in self._rows:
            if rect.contains(pos):
                self.setToolTip(item["text"])
                break
        else:
            self.setToolTip("Tuck the note away (bring it back from the paw menu)"
                            if self._tuck.contains(pos) else "")

    # MARK: - Drawing

    def paintEvent(self, event):
        p = QPainter(self)
        s = style.SHADOW
        card = QRectF(0, style.TAPE_OVERHANG, self.width() - s, self.height() - style.TAPE_OVERHANG - s)
        p.fillRect(card.translated(s, s), style.INK)
        p.fillRect(card, style.PAPER)
        half = style.BORDER / 2
        p.setPen(QPen(style.INK, style.BORDER))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(card.adjusted(half, half, -half, -half))

        # Tape across the top.
        tape = QRectF(card.center().x() - 30, 0, 60, 14)
        p.fillRect(tape, style.ACCENT)
        p.setPen(QPen(style.INK, 2))
        p.drawRect(tape.adjusted(1, 1, -1, -1))

        # Title, count and the tuck-away button.
        p.setFont(style.font(18, QFont.Weight.Bold))
        p.setPen(style.INK)
        p.drawText(QRectF(PAD, self._title_y, 120, 24), Qt.AlignmentFlag.AlignVCenter, "Today")
        p.drawText(self._tuck, Qt.AlignmentFlag.AlignCenter, "–")
        if self.list.items:
            p.setFont(style.font(14, QFont.Weight.DemiBold))
            p.drawText(QRectF(self._tuck.left() - 64, self._title_y + 3, 58, 20),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{self.list.done_count} / {len(self.list.items)}")
        if self._hint_y is not None:
            p.setFont(style.font(13, QFont.Weight.Medium))
            p.setPen(style.MUTED)
            p.drawText(QRectF(PAD, self._hint_y, card.width(), 20), Qt.AlignmentFlag.AlignVCenter,
                       "Nothing yet. What's on today?")

        for rect, item in self._rows:
            self._draw_row(p, rect, item)

        # Dashed line above the progress row.
        pen = QPen(style.INK, 2)
        pen.setDashPattern([2.5, 2])
        p.setPen(pen)
        p.drawLine(QPointF(16, self._separator_y), QPointF(card.right() - 16, self._separator_y))

        if self._paws_y is not None:
            total, done = len(self.list.items), self.list.done_count
            size = 16 if total > 7 else 20
            for i in range(total):
                style.fill_pixels(p, style.PAW, QRectF(PAD + i * (size + 4), self._paws_y + (20 - size) / 2,
                                                       size, size), 8,
                                  style.PAW_DONE if i < done else style.PAW_EMPTY)

        # The add-a-task box.
        p.fillRect(self._field_box, QColor("white"))
        p.setPen(QPen(style.INK, 2))
        p.drawRect(self._field_box.adjusted(1, 1, -1, -1))

    def _draw_row(self, p, rect, item):
        box = QRectF(rect.left(), rect.top() + 5, 18, 18)
        p.fillRect(box, style.ACCENT if item["done"] else QColor("white"))
        p.setPen(QPen(style.INK, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(box.adjusted(1, 1, -1, -1))
        if item["done"]:
            style.fill_pixels(p, style.TICK, box.adjusted(4, 4, -4, -4), 8, style.INK)
        f = style.font(14, QFont.Weight.DemiBold)
        f.setStrikeOut(item["done"])
        p.setFont(f)
        p.setPen(style.MUTED if item["done"] else style.INK)
        text_rect = QRectF(rect.left() + 28, rect.top() + 4, rect.width() - 28, 21)
        text = QFontMetrics(f).elidedText(item["text"], Qt.TextElideMode.ElideRight, round(text_rect.width()))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
