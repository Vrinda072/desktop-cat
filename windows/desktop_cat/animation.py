"""Reads animations.json, loads the frames and steps through them."""
import json
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QImage

from . import resources

#: The cat's states. Each one has an entry with the same name in animations.json.
STATES = ["curledSleeping", "stretching", "yawning", "curious", "happy", "awake", "resting", "walking",
          "blanket", "paperPlay", "paperChase", "paperEnd"]


@dataclass
class AnimationSpec:
    folder: str
    fps: float
    loop: bool
    start: int = 0
    end: int | None = None
    offsetY: float = 0   # points, positive moves the sprite up


class Manifest:
    def __init__(self):
        data = json.loads(resources.url("animations.json").read_text(encoding="utf-8"))
        #: Points per frame pixel. 0.5 means the frames are @2x art.
        self.points_per_pixel = float(data["pointsPerPixel"])
        self.animations = {}
        for name, raw in data["animations"].items():
            self.animations[name] = AnimationSpec(
                folder=raw["folder"], fps=float(raw["fps"]), loop=bool(raw["loop"]),
                start=int(raw.get("start", 0)), end=raw.get("end"), offsetY=float(raw.get("offsetY") or 0))
        missing = [s for s in STATES if s not in self.animations]
        if missing:
            raise SystemExit(f"animations.json has no entry for {', '.join(missing)}")

    def spec(self, state: str) -> AnimationSpec:
        return self.animations[state]


class FrameStore:
    """Loads decoded frames and keeps the most recently used folders in memory."""

    MAX_FOLDERS = 3

    def __init__(self):
        self._cache: dict[str, list[QImage]] = {}
        self._recent: list[str] = []

    def frames(self, spec: AnimationSpec) -> list[QImage]:
        frames = self._folder_frames(spec.folder)
        if not frames:
            return []
        first = min(max(spec.start, 0), len(frames) - 1)
        last = min(spec.end if spec.end is not None else len(frames) - 1, len(frames) - 1)
        return frames[first:max(first, last) + 1]

    def _folder_frames(self, folder: str) -> list[QImage]:
        if folder in self._recent:
            self._recent.remove(folder)
        self._recent.append(folder)
        if folder in self._cache:
            return self._cache[folder]
        directory = resources.ANIMATIONS / folder
        frames = []
        while True:
            path = directory / f"frame_{len(frames):03d}.png"
            image = QImage(str(path))
            if image.isNull():
                break
            frames.append(image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
        if not frames:
            print(f"DesktopCat: no frames found in {directory}")
        self._cache[folder] = frames
        while len(self._recent) > self.MAX_FOLDERS:
            self._cache.pop(self._recent.pop(0), None)
        return frames


class SpritePlayer(QObject):
    """Steps through frames at the animation's frame rate and tells the view to redraw."""

    def __init__(self, on_frame):
        super().__init__()
        self._on_frame = on_frame
        self._frames: list[QImage] = []
        self._index = 0
        self._loop = True
        self._on_finish = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    @property
    def current_image(self) -> QImage | None:
        return self._frames[self._index] if 0 <= self._index < len(self._frames) else None

    def play(self, frames, fps, loop, on_finish):
        self._timer.stop()
        self._frames = frames
        self._loop = loop
        self._on_finish = on_finish
        self._index = 0
        self._on_frame()
        # A single looping frame is a still pose and needs no timer.
        if len(frames) <= 1 and loop:
            return
        self._timer.start(max(1, round(1000 / max(fps, 1))))

    def _advance(self):
        if self._index + 1 < len(self._frames):
            self._index += 1
            self._on_frame()
        elif self._loop:
            self._index = 0
            self._on_frame()
        else:
            self._timer.stop()
            finish, self._on_finish = self._on_finish, None
            if finish:
                finish()
