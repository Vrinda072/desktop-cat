"""Colours and fonts shared by the bubble and the note, matching the cat's pixel look."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont

INK = QColor("#2A272E")
PAPER = QColor("#FFF1C9")
ACCENT = QColor("#9A9CA8")
PAW_DONE = QColor("#5E6070")
PAW_EMPTY = QColor("#E2D3AC")
MUTED = QColor("#6B6670")

#: Width of the hard offset shadow under the card.
SHADOW = 5
#: How far the strip of tape sticks out above the card.
TAPE_OVERHANG = 7
BORDER = 2.5

PAW = [(1, 1, 1, 2), (3, 0, 1, 2), (4, 0, 1, 2), (6, 1, 1, 2), (2, 4, 4, 3), (1, 5, 6, 1)]
TICK = [(0, 3, 1, 2), (1, 4, 1, 2), (2, 5, 1, 2), (3, 4, 1, 2), (4, 3, 1, 2), (5, 2, 1, 2), (6, 1, 1, 2), (7, 0, 1, 2)]


def font(size: float, weight: QFont.Weight) -> QFont:
    f = QFont("Segoe UI")
    # Segoe UI reads a touch small at these sizes, so nudge it up.
    f.setPixelSize(round(size * 1.15))
    f.setWeight(weight)
    return f


def fill_pixels(painter, cells, rect: QRectF, grid: float, color: QColor):
    """Fills cells of an 8×8 pixel pattern (x, y, width, height, top-left origin) inside rect."""
    unit = rect.width() / grid
    for x, y, w, h in cells:
        painter.fillRect(QRectF(rect.x() + x * unit, rect.y() + y * unit, w * unit, h * unit), color)
