"""The cat's window and the state machine that runs her.

curledSleeping --hover--> one random action (+ a message, if the cooldown allows) -> curledSleeping
Clicking shows a message (with the same cooldown).
Every 5 minutes she wakes up and walks to the other side of the screen (no message), then sleeps
there; now and then she chases a paper ball across instead. Hovering does nothing while she walks.
Timed messages and reminders play a short pose and speak, then she goes back to sleep.
Her to-do note sits beside her. At the check-in times she asks about an unfinished task by name,
she celebrates each one that gets ticked off, and she passes on nudges from the sheet.
Sleep Mode tucks her in under a blanket: no walks, no actions, nothing said unless she's clicked,
except nudges and live messages, which still come through.
"""
import math
import random
import time
from datetime import datetime

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QTransform
from PySide6.QtWidgets import QWidget

from .animation import FrameStore, Manifest, SpritePlayer
from .bubble import SpeechBubble
from .messages import LiveMessages, Messages, Reminders, RemoteControl, RemoteMessages
from .note import TodoNote
from .resources import config, settings
from .todos import CheckIns, TodoList

#: Size choices offered in the menu, as a multiple of the art's natural size.
SIZES = [("Small", 0.7), ("Medium", 1.0), ("Large", 1.4), ("Extra Large", 1.8)]
#: Message interval choices offered in the menu, in minutes.
MESSAGE_INTERVALS = [5, 15, 30, 60]

FAR_FUTURE = float("inf")
#: Animations that move her across the screen.
WALKS = {"walking", "paperChase"}
#: Everything that's part of a walk, start to finish. She stays quiet through all of it.
OUT_AND_ABOUT = WALKS | {"paperPlay", "paperEnd"}


class CatWindow(QWidget):
    """Borderless, transparent, always-on-top window that never takes focus. Clicks on fully
    transparent pixels fall through to whatever is behind (Windows does that for per-pixel-alpha
    windows by itself)."""

    moved = Signal()

    def __init__(self, size):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)   # (macOS hides tool windows otherwise)
        self.resize(size)
        self.image = None
        self.offset_y = 0.0
        self.facing_left = False
        self.is_tracking = False
        self.on_click = None
        self.on_drag_end = None
        self.on_menu = None
        self._down_global = QPoint()
        self._origin_at_down = QPoint()
        self._dragged = False

    def set_image(self, image):
        self.image = image
        self.update()

    def _sprite_rect(self) -> QRectF:
        return QRectF(0, -self.offset_y, self.width(), self.height())

    def paintEvent(self, event):
        if self.image is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.facing_left:   # mirror so the walking cat faces left
            p.setTransform(QTransform(-1, 0, 0, 1, self.width(), 0))
        p.drawImage(self._sprite_rect(), self.image)

    def hits_cat(self, global_pos: QPoint) -> bool:
        """True when the point lands on a visible pixel of the cat."""
        if self.image is None:
            return False
        local = QPointF(self.mapFromGlobal(global_pos))
        rect = self._sprite_rect()
        if self.facing_left:
            local.setX(self.width() - local.x())
        if not rect.contains(local) or rect.width() <= 0:
            return False
        x = int((local.x() - rect.x()) / rect.width() * self.image.width())
        y = int((local.y() - rect.y()) / rect.height() * self.image.height())
        x = min(max(x, 0), self.image.width() - 1)
        y = min(max(y, 0), self.image.height() - 1)
        return (self.image.pixel(x, y) >> 24) > 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self.on_menu:
                self.on_menu(event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.is_tracking = True
        self._dragged = False
        self._down_global = event.globalPosition().toPoint()
        self._origin_at_down = self.pos()

    def mouseMoveEvent(self, event):
        if not self.is_tracking:
            return
        delta = event.globalPosition().toPoint() - self._down_global
        if not self._dragged and math.hypot(delta.x(), delta.y()) < 3:
            return
        self._dragged = True
        self.move(self._origin_at_down + delta)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.is_tracking:
            return
        self.is_tracking = False
        if self._dragged:
            if self.on_drag_end:
                self.on_drag_end()
        elif self.on_click:
            self.on_click()

    def moveEvent(self, event):
        self.moved.emit()


class CatController:
    # Timing knobs, in seconds.
    #: Minimum gap between messages from hovering or clicking.
    INTERACTIVE_COOLDOWN = 2 * 60
    #: How long the resting pose lasts before she curls back up.
    RESTING_LINGERS = 6
    HOVER_DWELL = 0.4
    WALK_SPEED = 60     # logical pixels per second
    CHASE_SPEED = 180   # she runs after her paper ball
    WALK_MARGIN = 40    # how far from the screen edge she stops
    PAPER_CHANCE = 0.35 # how often a walk is a paper-ball chase instead
    LIVE_EVERY = 10     # seconds between looks at the sheet's Live tab
    LIVE_LINES = 5      # how many recent live lines her bubble keeps

    def __init__(self):
        self.manifest = Manifest()
        self.frames = FrameStore()
        self.messages = Messages()
        self.remote_messages = RemoteMessages(self.messages)
        self.reminders = Reminders()
        self.todos = TodoList()
        self.note = TodoNote(self.todos)
        self.bubble = SpeechBubble()
        self.remote_control = RemoteControl(self._nudge_arrived)
        self.live = LiveMessages(self._nudge_arrived)

        first = self.frames.frames(self.manifest.spec("resting"))
        pixels = (first[0].width(), first[0].height()) if first else (427, 367)
        self.base_size = (pixels[0] * self.manifest.points_per_pixel, pixels[1] * self.manifest.points_per_pixel)
        self.window = CatWindow(self._size_for(self.scale))
        self.player = SpritePlayer(lambda: self.window.set_image(self.player.current_image))

        self.state = self._rest_state
        self.state_entered_at = time.time()
        self.queue: list[str] = []
        self.pending_nudge = None
        self.next_nudge_dance = FAR_FUTURE
        self.check_in_after_nudge = None
        self.hold_chatter_until = 0.0
        self.hover_started_at = None
        self.hover_armed = True
        self.next_message_at = 0.0
        self.last_interactive_message_at = -FAR_FUTURE
        self.next_walk_at = FAR_FUTURE
        self.walking_right = True
        self._walk_x = None   # sub-pixel position while walking
        self.ball_next = False   # the menu asked for the paper ball while she was busy
        self._walk_last = 0.0
        self.on_menu = None

        self.window.on_click = self._clicked
        self.window.on_drag_end = self._drag_ended
        self.window.on_menu = lambda pos: self.on_menu and self.on_menu(pos)
        self.window.moved.connect(self._window_moved)
        self.note.on_toggle = self._task_toggled
        self.note.on_add = lambda item: self._task_added()
        self.bubble.on_pinned_click = self._dismiss_nudge

        self._tick_timer = QTimer(timeout=self._tick)
        self._hover_timer = QTimer(timeout=self._update_hover)
        self._walk_timer = QTimer(timeout=self._step_walk)
        self._sheet_timer = QTimer(timeout=self.refresh_sheet)
        self._live_timer = QTimer(timeout=self.live.refresh)

    # MARK: - Settings

    @property
    def walk_interval(self) -> float:
        saved = float(settings.get("walkEverySeconds", 0) or 0)   # hidden, for testing
        return saved if saved > 0 else 5 * 60

    @property
    def message_minutes(self) -> int:
        return int(settings.get("messageMinutes", 15) or 15)

    @message_minutes.setter
    def message_minutes(self, value):
        settings.set("messageMinutes", int(value))
        self._schedule_next_message()

    @property
    def reminders_on(self) -> bool:
        return bool(settings.get("remindersOn", True))

    @reminders_on.setter
    def reminders_on(self, value):
        settings.set("remindersOn", bool(value))
        if value:
            self.reminders.restart()

    @property
    def is_quiet(self) -> bool:
        return bool(settings.get("quiet", False))

    @is_quiet.setter
    def is_quiet(self, value):
        settings.set("quiet", bool(value))
        if value:
            self.bubble.hide_bubble()

    @property
    def sleep_mode(self) -> bool:
        return bool(settings.get("sleepMode", False))

    @sleep_mode.setter
    def sleep_mode(self, value):
        settings.set("sleepMode", bool(value))
        self.queue = []
        if value:
            self.bubble.hide_bubble()
            self.window.facing_left = False
            self._enter("blanket")   # straight under the blanket, even mid-walk
        else:
            # Wide awake again: everything restarts its clock rather than all going off at once.
            self.next_walk_at = time.time() + self.walk_interval
            self._schedule_next_message()
            self._enter("curledSleeping")

    @property
    def scale(self) -> float:
        saved = float(settings.get("catScale", 1) or 1)
        return saved if saved > 0 else 1

    @scale.setter
    def scale(self, value):
        settings.set("catScale", float(value))
        self._apply_scale()

    @property
    def is_note_open(self) -> bool:
        return self.note.is_open

    @is_note_open.setter
    def is_note_open(self, value):
        self.note.set_open(value)

    def _size_for(self, scale):
        return QSize(math.ceil(self.base_size[0] * scale), math.ceil(self.base_size[1] * scale))

    def _schedule_next_message(self):
        self.next_message_at = time.time() + self.message_minutes * 60

    # MARK: - Start

    def start(self):
        self.window.move(self._saved_or_default_origin())
        self.window.show()
        self._schedule_next_message()
        self.reminders.restart()
        self.refresh_sheet()
        self._sheet_timer.start(60_000)   # re-read the sheet every minute
        self.live.refresh()
        self._live_timer.start(self.LIVE_EVERY * 1000)   # and the Live tab every few seconds
        self.note.attach(self.window)
        self.next_walk_at = time.time() + self.walk_interval
        self._enter(self._rest_state)
        self._tick_timer.start(1000)
        self._hover_timer.start(1000 // 15)

    # MARK: - State machine

    def _enter(self, state):
        self.state = state
        self.state_entered_at = time.time()
        spec = self.manifest.spec(state)
        if state not in WALKS:
            self._stop_walking()
        self.window.offset_y = spec.offsetY * self.scale
        self.player.play(self.frames.frames(spec), spec.fps, spec.loop, lambda: self._finished(state))

    def _finished(self, state):
        if state == self.state:
            self._advance()

    def _advance(self):
        """Plays the next animation in the sequence, or goes back to sleep when it's done. If a
        walk came due during an action, she sets off as soon as it ends."""
        if self.state == "paperPlay" and not self.sleep_mode:
            self._begin_walk("paperChase")   # done batting it about: after it!
        elif self.queue and not self.sleep_mode:
            self._enter(self.queue.pop(0))
        elif self.ball_next and not self.sleep_mode:
            self.ball_next = False
            self._start_walking(with_ball=True)
        elif time.time() >= self.next_walk_at and not self.sleep_mode:
            self._start_walking()
        else:
            self.queue = []
            self.window.facing_left = False
            self._enter(self._rest_state)

    @property
    def _rest_state(self) -> str:
        return "blanket" if self.sleep_mode else "curledSleeping"

    def _act(self, sequence) -> bool:
        """Starts a sequence, but only while she's asleep, so a sequence always plays to the end.
        In Sleep Mode she stays tucked in and doesn't act at all."""
        if self.state != "curledSleeping" or not sequence or self.sleep_mode:
            return False
        self.queue = list(sequence[1:])
        self._enter(sequence[0])
        return True

    def _hovered(self):
        if self._act([random.choice(["stretching", "yawning", "curious", "happy", "awake", "resting"])]):
            self._say_interactive(force=False)

    def _clicked(self):
        if self.bubble.is_pinned:
            self._dismiss_nudge()
            return
        if self.state not in OUT_AND_ABOUT:   # walks are silent
            self._say_interactive(force=True)

    def _tick(self):
        now = time.time()
        if self.state == "resting" and now - self.state_entered_at > self.RESTING_LINGERS:
            self._advance()
        # She stays put while a nudge is up, so it isn't carried off across the screen.
        if (self.state == "curledSleeping" and now >= self.next_walk_at and not self.bubble.is_pinned
                and not self.sleep_mode):
            self._start_walking(with_ball=random.random() < self.PAPER_CHANCE)
        if self.state in OUT_AND_ABOUT:
            return

        self.todos.roll_over_if_new_day()
        pinned = self.bubble.is_pinned
        if self.pending_nudge and (pinned or now >= self.hold_chatter_until):
            nudge, self.pending_nudge = self.pending_nudge, None
            self._deliver_nudge(nudge)
            return
        if self.sleep_mode:
            return   # tucked in: only clicks, nudges and live messages get through
        if pinned or now >= self.hold_chatter_until:
            is_last = CheckIns.due(datetime.now())
            if is_last is not None:
                self._check_in(is_last)
        if self.bubble.is_pinned:
            # Nothing else talks over a nudge; she just keeps dancing next to it.
            if now >= self.next_nudge_dance:
                self._act(["happy"])
                self.next_nudge_dance = now + 60
            return
        if now < self.hold_chatter_until:
            return

        if now > self.next_message_at:
            self._schedule_next_message()
            text = None if self.is_quiet else self.messages.next()
            if text:
                self._act(["resting"])
                self.bubble.show_text(text, self.window)

        if self.reminders_on:
            reminder = self.reminders.due(now)
            if reminder and not self.is_quiet:
                animation = reminder.get("animation")
                self._act([animation if animation in self.manifest.animations else "resting"])
                self.bubble.show_text(reminder["text"], self.window)

    # MARK: - Walking

    def _screen_rect(self) -> QRect:
        screen = self.window.screen() or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _start_walking(self, with_ball=False):
        """Walks to the far side of the screen (the side with more room). With the ball, she first
        bats it about where she is, then chases it across."""
        self.queue = []
        self.bubble.hide_bubble()
        screen, frame = self._screen_rect(), self.window.frameGeometry()
        self.walking_right = screen.right() - frame.right() >= frame.left() - screen.left()
        if with_ball:
            self._enter("paperPlay")
            self.window.facing_left = not self.walking_right   # the ball goes the way she's going
            self.window.update()
        else:
            self._begin_walk("walking")

    def _begin_walk(self, animation):
        self._enter(animation)
        self._walk_last = time.time()
        self._walk_timer.start(1000 // 30)

    def play_with_ball(self):
        """From the menu: she chases her paper ball across the screen (if she's free to)."""
        if self.sleep_mode:
            self.show("Zzz... I'm all tucked in. Maybe after my nap.")
        elif self.state == "curledSleeping":
            self._start_walking(with_ball=True)
        elif self.state not in OUT_AND_ABOUT:
            self.ball_next = True   # busy with something quick: she goes for it right after

    def _step_walk(self):
        now = time.time()
        dt, self._walk_last = min(now - self._walk_last, 0.2), now
        if self.window.is_tracking:   # being dragged: carry on from wherever she's dropped
            return
        screen, frame = self._screen_rect(), self.window.frameGeometry()
        # Worked out every step, so resizing or dragging her mid-walk still ends on screen.
        target_x = (screen.right() + 1 - frame.width() - self.WALK_MARGIN if self.walking_right
                    else screen.left() + self.WALK_MARGIN)
        if self._walk_x is None or abs(self._walk_x - frame.x()) >= 1:
            self._walk_x = float(frame.x())
        remaining = target_x - self._walk_x
        step = (self.CHASE_SPEED if self.state == "paperChase" else self.WALK_SPEED) * dt
        self.window.facing_left = remaining < 0   # the walking art faces right
        if abs(remaining) <= step:
            self._walk_x = None
            self.window.move(target_x, frame.y())
            if self.state == "paperChase":
                facing = self.window.facing_left
                self._enter("paperEnd")   # sits back with her ball, still facing the way she went
                self.window.facing_left = facing
                self.window.update()
            else:
                self._enter(self._rest_state)
        else:
            self._walk_x += -step if remaining < 0 else step
            self.window.move(round(self._walk_x), frame.y())

    def _stop_walking(self):
        if not self._walk_timer.isActive():
            return
        self._walk_timer.stop()
        self._walk_x = None
        self.window.facing_left = False
        self.next_walk_at = time.time() + self.walk_interval
        self._save_position()

    # MARK: - To-do list

    def on_note_open_change(self, handler):
        self.note.on_open_change = handler

    def _task_toggled(self, item, done):
        if not done:
            return
        left = len(self.todos.open)
        self._act(["happy"])
        if left == 0:
            self.bubble.show_text("All done! I'm so proud of you.", self.window)
        elif left == 1:
            self.bubble.show_text("You did it! Just one to go.", self.window)
        else:
            self.bubble.show_text(f"You did it! {left} to go.", self.window)

    def _task_added(self):
        # The first task of an empty list gets a little hello; after that she stays quiet.
        if len(self.todos.items) == 1:
            self.bubble.show_text("Got it. I'll keep an eye on it for you.", self.window)

    def _check_in(self, is_last):
        """Asks about the oldest unfinished task by name."""
        open_items = self.todos.open
        if not self.todos.items:
            if is_last:
                return   # too late in the day to start a list
            text = "What are we doing today? Add a task to my note."
        elif open_items:
            first = open_items[0]["text"]
            if is_last:
                text = (f'Last call! Did "{first}" happen?' if len(open_items) == 1
                        else f'Last call! {len(open_items)} left, starting with "{first}".')
            else:
                text = f'Psst. Did "{first}" happen yet?'
        else:
            return   # everything's done; let her be
        if not self.note.is_open:
            self.note.set_open(True)
        if self.is_quiet:
            return
        if self.bubble.is_pinned:
            self.check_in_after_nudge = text   # the nudge stays up; she asks once it's read
            return
        self._act(["curious"])
        self.bubble.show_text(text, self.window)
        self.hold_chatter_until = time.time() + 20

    def _nudge_arrived(self, text):
        # Several can arrive before she's free to show them (e.g. during a walk); keep them all.
        self.pending_nudge = f"{self.pending_nudge}\n{text}" if self.pending_nudge else text

    def _deliver_nudge(self, text):
        """A nudge or live message. Said even in Quiet Mode, in a pink signed bubble that stays up
        until it's clicked, with a happy dance every minute until then. If one is already up, the
        new lines are added under it, so a quick back-and-forth reads like a chat."""
        if self.bubble.is_pinned:
            text = f"{self.bubble.text}\n{text}"
        text = "\n".join(text.split("\n")[-self.LIVE_LINES:])
        self._act(["happy"])
        sender = (settings.get("nudgeFrom") or config.get("nudgeFrom") or "").strip()
        self.bubble.show_pinned(text, f"from {sender} 💌" if sender else "💌", self.window)
        self.next_nudge_dance = time.time() + 60

    def _dismiss_nudge(self):
        self.bubble.unpin()
        self.next_nudge_dance = FAR_FUTURE
        self.hold_chatter_until = time.time() + 20
        if self.check_in_after_nudge:
            text, self.check_in_after_nudge = self.check_in_after_nudge, None
            self._act(["curious"])
            self.bubble.show_text(text, self.window)

    # MARK: - Messages

    def say(self):
        text = self.messages.next()
        if text:
            self.bubble.show_text(text, self.window)

    def show(self, text):
        self.bubble.show_text(text, self.window)

    def set_messages_link(self, text) -> bool:
        if not self.remote_messages.set_link(text):
            return False
        self.remote_control.refresh()
        return True

    def refresh_sheet(self):
        self.remote_messages.refresh()
        self.remote_control.refresh()

    def _say_interactive(self, force):
        """Hover and click messages share one cooldown so they can't pile up."""
        if self.is_quiet and not force:
            return
        if time.time() - self.last_interactive_message_at < self.INTERACTIVE_COOLDOWN:
            return
        self.last_interactive_message_at = time.time()
        self.say()

    # MARK: - Hover

    def _update_hover(self):
        if self.window.is_tracking:
            self.hover_armed = False   # a drag shouldn't also trigger an action
            return
        mouse = QCursor.pos()
        in_window = self.window.frameGeometry().contains(mouse)
        over_cat = in_window and self.window.hits_cat(mouse)
        if not over_cat:
            self.hover_started_at = None
            if not in_window:
                self.hover_armed = True
            return
        # Pressing the button (to drag) uses up this hover.
        if QGuiApplication.mouseButtons() != Qt.MouseButton.NoButton:
            self.hover_armed = False
        if not self.hover_armed:
            return
        if self.hover_started_at is None:
            self.hover_started_at = time.time()
        if time.time() - self.hover_started_at >= self.HOVER_DWELL:
            self.hover_armed = False
            self._hovered()

    # MARK: - Position

    def _window_moved(self):
        self.note.place()
        if self.bubble.isVisible():
            self.bubble.reposition()

    def _drag_ended(self):
        self._save_position()
        self.note.place()

    def _apply_scale(self):
        """Resizes her, keeping her feet in place."""
        size = self._size_for(self.scale)
        old = self.window.frameGeometry()
        frame = QRect(round(old.center().x() - size.width() / 2), old.bottom() + 1 - size.height(),
                      size.width(), size.height())
        screen = self._screen_rect()
        frame.moveLeft(min(max(frame.left(), screen.left()), screen.right() + 1 - frame.width()))
        frame.moveTop(min(max(frame.top(), screen.top()), screen.bottom() + 1 - frame.height()))
        self.window.setGeometry(frame)
        self.window.offset_y = self.manifest.spec(self.state).offsetY * self.scale
        self.window.update()
        self._save_position()
        self.note.place()
        self.note.raise_()
        self.window.raise_()

    def reset_position(self):
        self.window.move(self._default_origin())
        self._save_position()

    def _save_position(self):
        frame = self.window.frameGeometry()
        # The bottom-left corner, so a size change keeps her on the same spot.
        settings.set("catOrigin", [frame.left(), frame.bottom() + 1])

    def _saved_or_default_origin(self) -> QPoint:
        saved = settings.get("catOrigin")
        size = self.window.size()
        if isinstance(saved, list) and len(saved) == 2:
            origin = QPoint(int(saved[0]), int(saved[1]) - size.height())
            frame = QRect(origin, size)
            # Only reuse it if the cat would still be on a connected screen.
            if any(s.availableGeometry().intersects(frame) for s in QGuiApplication.screens()):
                return origin
        return self._default_origin()

    def _default_origin(self) -> QPoint:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        size = self.window.size()
        return QPoint(screen.right() + 1 - size.width() - 40, screen.bottom() + 1 - size.height() - 10)
