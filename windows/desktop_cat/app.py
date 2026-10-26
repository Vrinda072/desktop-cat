"""Startup and the tray icon."""
import sys

from PySide6.QtCore import QLockFile, QRectF, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QSystemTrayIcon

from . import APP_NAME, resources, style
from .cat import MESSAGE_INTERVALS, SIZES, CatController

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def paw_icon() -> QIcon:
    """A pixel paw print for the tray, light with a dark outline so it shows on any taskbar."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 48):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        unit = size / 10
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            style.fill_pixels(p, style.PAW, QRectF(unit * (1 + dx * 0.6), unit * (1.5 + dy * 0.6), unit * 8, unit * 8),
                              8, QColor("#2A272E"))
        style.fill_pixels(p, style.PAW, QRectF(unit, unit * 1.5, unit * 8, unit * 8), 8, QColor("#E6E6EC"))
        p.end()
        icon.addPixmap(pixmap)
    return icon


def start_with_windows() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_start_with_windows(on: bool):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


class Tray:
    def __init__(self, cat: CatController):
        self.cat = cat
        self.menu = QMenu()
        self.tray = QSystemTrayIcon(paw_icon())
        self.tray.setToolTip(APP_NAME)

        self.note_item = self._check("To-Do Note", cat.is_note_open, self._toggle_note)
        cat.on_note_open_change(lambda: self.note_item.setChecked(cat.is_note_open))
        self.menu.addSeparator()
        self.menu.addAction("Say Something", cat.say)
        self.menu.addAction("Play With Paper Ball", cat.play_with_ball)
        self.sleep_item = self._check("Sleep Mode (tucked in, only speaks when clicked)", cat.sleep_mode,
                                      self._toggle_sleep)
        self.quiet_item = self._check("Quiet Mode (only speaks when clicked)", cat.is_quiet, self._toggle_quiet)
        self.reminders_item = self._check("Water && Stretch Reminders", cat.reminders_on, self._toggle_reminders)
        self.menu.addAction("Bring Cat Back", cat.reset_position)

        size_menu = self.menu.addMenu("Size")
        group = QActionGroup(size_menu)
        for name, scale in SIZES:
            action = size_menu.addAction(name, lambda s=scale: setattr(cat, "scale", s))
            action.setCheckable(True)
            action.setChecked(abs(scale - cat.scale) < 0.01)
            group.addAction(action)

        interval_menu = self.menu.addMenu("Messages")
        group = QActionGroup(interval_menu)
        for minutes in MESSAGE_INTERVALS:
            title = f"Every {minutes} Minutes" if minutes < 60 else "Every Hour"
            action = interval_menu.addAction(title, lambda m=minutes: setattr(cat, "message_minutes", m))
            action.setCheckable(True)
            action.setChecked(minutes == cat.message_minutes)
            group.addAction(action)

        self.menu.addSeparator()
        self.menu.addAction("Set Messages Link…", self._set_messages_link)
        if sys.platform == "win32":
            self._check("Start with Windows", start_with_windows(), self._toggle_startup)
        self.menu.addSeparator()
        self.menu.addAction(f"Quit {APP_NAME}", QApplication.quit)

        self.tray.setContextMenu(self.menu)
        # A left click on the tray paw opens the menu too.
        self.tray.activated.connect(self._activated)
        self.tray.show()
        # Right-clicking the cat opens the same menu (the tray paw can hide in the ^ overflow).
        cat.on_menu = lambda pos: self.menu.popup(pos)

    def _check(self, title, checked, handler) -> QAction:
        action = self.menu.addAction(title)
        action.setCheckable(True)
        action.setChecked(checked)
        action.triggered.connect(handler)
        return action

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.menu.popup(self.tray.geometry().center())

    def _toggle_note(self):
        self.cat.is_note_open = not self.cat.is_note_open
        self.note_item.setChecked(self.cat.is_note_open)

    def _toggle_sleep(self):
        self.cat.sleep_mode = not self.cat.sleep_mode
        self.sleep_item.setChecked(self.cat.sleep_mode)

    def _toggle_quiet(self):
        self.cat.is_quiet = not self.cat.is_quiet
        self.quiet_item.setChecked(self.cat.is_quiet)

    def _toggle_reminders(self):
        self.cat.reminders_on = not self.cat.reminders_on
        self.reminders_item.setChecked(self.cat.reminders_on)

    def _toggle_startup(self, checked):
        try:
            set_start_with_windows(checked)
        except OSError as error:
            self.cat.show(f"I couldn't change that: {error}")

    def _set_messages_link(self):
        from .messages import RemoteMessages
        text, ok = QInputDialog.getText(
            None, "Messages Link",
            "Paste the link to the messages sheet. Leave it empty to use the built-in messages.",
            text=RemoteMessages.link())
        if not ok:
            return
        if self.cat.set_messages_link(text):
            self.cat.show("Okay, back to my usual messages." if not text.strip() else "Got it! New messages coming up.")
        else:
            self.cat.show("That doesn't look like a link. It should start with https://")


def main():
    if sys.platform == "win32":
        # Its own taskbar/notification identity rather than "python".
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DesktopCat.Windows")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    if resources.ICON.exists():
        app.setWindowIcon(QIcon(str(resources.ICON)))

    # Only one cat at a time.
    resources.DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(resources.DATA_FOLDER / "running.lock"))
    if not lock.tryLock(100):
        return 0

    cat = CatController()
    cat.start()
    app.tray = Tray(cat)   # kept alive for the app's lifetime
    return app.exec()
