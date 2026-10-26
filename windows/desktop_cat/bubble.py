"""A small rounded speech bubble shown in its own window above the cat.

A pinned bubble (a nudge from the sheet) is tinted, signed, and stays up until it or the cat is
clicked. While it's up, ordinary lines and hides are ignored so nothing covers it.
"""
from PySide6.QtCore import QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import style

TAIL = 10
PADDING = 12
MAX_TEXT_WIDTH = 200
WHITE = QColor("white")
PINK = QColor.fromRgbF(1.0, 0.92, 0.95)
PINK_EDGE = QColor.fromRgbF(0.80, 0.40, 0.55)
SIGNATURE = QColor.fromRgbF(0.62, 0.25, 0.40)
EDGE = QColor.fromRgbF(0.25, 0.25, 0.25)
TEXT = QColor.fromRgbF(0.15, 0.15, 0.15)


class SpeechBubble(QWidget):
    def __init__(self):
        super().__init__(None, self._flags(pinned=False))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)   # (macOS hides tool windows otherwise)
        self.is_pinned = False
        self.on_pinned_click = None
        self._text = ""
        self._signature = ""
        self._cat = None
        self._anchor_x = 0.6
        self._text_font = style.font(13, QFont.Weight.Medium)
        self._sig_font = style.font(11, QFont.Weight.Normal)
        self._hide_timer = QTimer(self, singleShot=True, timeout=self.hide_bubble)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.finished.connect(self._fade_finished)

    @staticmethod
    def _flags(pinned: bool):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
                 | Qt.WindowType.NoDropShadowWindowHint)
        if not pinned:   # clicks go through an ordinary bubble
            flags |= Qt.WindowType.WindowTransparentForInput
        return flags

    @property
    def text(self) -> str:
        return self._text

    def show_text(self, text: str, cat: QWidget):
        """Ignored while a pinned bubble is up."""
        if not self.is_pinned:
            self._present(text, None, cat)

    def show_pinned(self, text: str, signed_by: str, cat: QWidget):
        self._present(text, signed_by, cat)

    def unpin(self):
        if self.is_pinned:
            self.is_pinned = False
            self.hide_bubble()

    def _present(self, text, signed_by, cat):
        self._hide_timer.stop()
        self._fade.stop()
        pinned = signed_by is not None
        if pinned != self.is_pinned or self.windowFlags() != self._flags(pinned):
            self.setWindowFlags(self._flags(pinned))
        self.is_pinned = pinned
        self._text = text
        self._signature = signed_by or ""
        self._cat = cat
        self._layout()
        self.reposition()
        self.setWindowOpacity(0)
        self.show()
        self._animate(1.0, 250)
        # Longer lines stay up a little longer; a pinned one stays until it's clicked.
        if not pinned:
            self._hide_timer.start(round((5 + len(text) / 20) * 1000))

    def _layout(self):
        text_rect = QFontMetrics(self._text_font).boundingRect(
            QRect(0, 0, MAX_TEXT_WIDTH, 1000), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter, self._text)
        self._text_size = (text_rect.width() + 2, text_rect.height())
        if self._signature:
            sig = QFontMetrics(self._sig_font).boundingRect(self._signature)
            self._sig_size = (sig.width() + 2, sig.height())
            gap = 4
        else:
            self._sig_size, gap = (0, 0), 0
        self._content_width = max(self._text_size[0], self._sig_size[0])
        self.resize(self._content_width + PADDING * 2,
                    self._text_size[1] + self._sig_size[1] + gap + PADDING * 2 + TAIL)

    def reposition(self):
        """Puts the bubble over the cat (also called when she moves)."""
        if self._cat is None:
            return
        cat = self._cat.frameGeometry()
        x = round(cat.x() + cat.width() * self._anchor_x - self.width() / 2)
        y = cat.y() + 24 - self.height()
        screen = (self._cat.screen() or self.screen()).availableGeometry()
        x = min(max(x, screen.left() + 4), screen.right() - self.width() - 4)
        y = max(y, screen.top() + 4)
        self.move(x, y)

    def hide_bubble(self):
        """Fades the bubble out, unless it's pinned."""
        if self.is_pinned:
            return
        self._hide_timer.stop()
        if not self.isVisible():
            return
        self._animate(0.0, 300)

    def _animate(self, to, ms):
        self._fade.stop()
        self._fade.setDuration(ms)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(to)
        self._fade.start()

    def _fade_finished(self):
        if self.windowOpacity() < 0.01 and not self.is_pinned:
            self.hide()
            self._text = ""

    def mousePressEvent(self, event):
        if self.is_pinned and self.on_pinned_click:
            self.on_pinned_click()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        body = QRectF(1, 1, w - 2, h - TAIL - 1)
        fill = PINK if self.is_pinned else WHITE
        edge = PINK_EDGE if self.is_pinned else EDGE
        path = QPainterPath()
        path.addRoundedRect(body, 12, 12)
        tail = QPainterPath()
        tail.moveTo(QPointF(body.center().x() - 8, body.bottom() - 1))
        tail.lineTo(QPointF(body.center().x() - 2, h - 1))
        tail.lineTo(QPointF(body.center().x() + 6, body.bottom() - 1))
        tail.closeSubpath()
        p.setPen(QPen(edge, 1.5))
        p.setBrush(fill)
        p.drawPath(tail)
        p.drawPath(path)
        # Paint over the border where the tail joins the body.
        p.fillRect(QRectF(body.center().x() - 6, body.bottom() - 1.5, 10, 3), fill)

        p.setPen(TEXT)
        p.setFont(self._text_font)
        text_rect = QRectF(PADDING + (self._content_width - self._text_size[0]) / 2, PADDING,
                           self._text_size[0], self._text_size[1])
        p.drawText(text_rect, Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter, self._text)
        if self._signature:
            p.setPen(SIGNATURE)
            p.setFont(self._sig_font)
            p.drawText(QRectF(PADDING, text_rect.bottom() + 4, self._content_width, self._sig_size[1]),
                       Qt.AlignmentFlag.AlignRight, self._signature)
