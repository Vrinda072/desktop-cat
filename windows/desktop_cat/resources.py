"""Finds the art and JSON files, and keeps her settings and saved data.

Bundled into the .exe by PyInstaller, everything sits next to each other in the unpacked folder.
Run from source, the grey frames come from windows/assets and the JSON files from windows/data.
"""
import json
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _BUNDLE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    ANIMATIONS = _BUNDLE / "Animations"
    _JSON = [_BUNDLE]
    ICON = _BUNDLE / "cat.ico"
else:
    _WINDOWS = Path(__file__).resolve().parents[1]
    ANIMATIONS = _WINDOWS / "assets" / "Animations"
    _JSON = [_WINDOWS / "data"]
    ICON = _WINDOWS / "assets" / "cat.ico"


def url(name: str) -> Path:
    """config.json, animations.json, messages.json or reminders.json."""
    for folder in _JSON:
        if (folder / name).exists():
            return folder / name
    return _JSON[0] / name


#: %APPDATA%\Desktop Cat: her to-do list, cached messages and settings. (Run from source on
#: another system, for trying it out, it uses a folder in the home directory.)
if os.environ.get("DESKTOP_CAT_DATA"):   # for tests
    DATA_FOLDER = Path(os.environ["DESKTOP_CAT_DATA"])
elif sys.platform == "win32":
    DATA_FOLDER = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Desktop Cat"
else:
    DATA_FOLDER = Path.home() / ".desktop-cat-windows-test"


def write_atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class Settings:
    """Her settings, kept in a small JSON file."""

    def __init__(self):
        self.path = DATA_FOLDER / "settings.json"
        try:
            self._values = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self._values, dict):
                self._values = {}
        except (OSError, ValueError):
            self._values = {}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        if value is None:
            self._values.pop(key, None)
        else:
            self._values[key] = value
        try:
            write_atomic(self.path, json.dumps(self._values, indent=2).encode("utf-8"))
        except OSError as error:
            print(f"DesktopCat: could not save settings: {error}", file=sys.stderr)

    def remove(self, key):
        self.set(key, None)


settings = Settings()


def _load_config() -> dict:
    try:
        config = json.loads(url("config.json").read_text(encoding="utf-8"))
        config = config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        config = {}
    # The sheet link isn't in the repo: it comes from link.txt, which the build writes from a
    # GitHub secret (or which you create yourself for a local build).
    try:
        link = url("link.txt").read_text(encoding="utf-8").strip()
        if link:
            config["messagesLink"] = link
    except OSError:
        pass
    return config


#: Built into the app from windows/data: the messages sheet link and the name nudges are signed
#: with. Settings chosen from the tray menu on the PC win over these.
config = _load_config()
