"""Her to-do list and the times of day she checks on it."""
import json
import sys
import uuid
from datetime import datetime, timedelta

from . import resources
from .resources import settings

FILE = resources.DATA_FOLDER / "todos.json"


class TodoList:
    """Today's tasks. On a new day, finished tasks are cleared and unfinished ones carry over."""

    MAX_ITEMS = 10

    def __init__(self):
        self.items: list[dict] = []   # {"id", "text", "done"}
        self._day = ""
        self.on_change = None
        try:
            saved = json.loads(FILE.read_text(encoding="utf-8"))
            self.items = [{"id": str(i.get("id") or uuid.uuid4()), "text": str(i["text"]),
                           "done": bool(i.get("done"))} for i in saved.get("items", [])]
            self._day = saved.get("day", "")
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            pass
        self.roll_over_if_new_day()

    @property
    def open(self):
        return [i for i in self.items if not i["done"]]

    @property
    def done_count(self):
        return sum(1 for i in self.items if i["done"])

    def add(self, text: str) -> bool:
        text = text.strip()
        if not text or len(self.items) >= self.MAX_ITEMS:
            return False
        self.items.append({"id": str(uuid.uuid4()).upper(), "text": text, "done": False})
        self._changed()
        return True

    def toggle(self, item_id) -> bool | None:
        for item in self.items:
            if item["id"] == item_id:
                item["done"] = not item["done"]
                self._changed()
                return item["done"]
        return None

    def remove(self, item_id):
        self.items = [i for i in self.items if i["id"] != item_id]
        self._changed()

    def roll_over_if_new_day(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if today == self._day:
            return
        self._day = today
        self.items = [i for i in self.items if not i["done"]]
        self._changed()

    def _changed(self):
        try:
            data = json.dumps({"day": self._day, "items": self.items}, indent=1)
            resources.write_atomic(FILE, data.encode("utf-8"))
        except OSError as error:
            print(f"DesktopCat: could not save the to-do list: {error}", file=sys.stderr)
        if self.on_change:
            self.on_change()


class CheckIns:
    """11:00, 15:00 and 19:00 unless the sheet says otherwise."""

    TIMES_KEY = "checkInTimes"
    LAST_KEY = "lastCheckIn"
    DEFAULT = [11 * 60, 15 * 60, 19 * 60]
    #: A check-in missed by more than this (the PC was asleep) is skipped.
    LATENESS = timedelta(hours=2)

    @classmethod
    def times(cls) -> list[int]:
        return cls.parse(settings.get(cls.TIMES_KEY, "")) or cls.DEFAULT

    @staticmethod
    def parse(text: str) -> list[int]:
        """Reads "11:00, 15:00", "11am, 3pm", "3:30 pm" or "14" (also with seconds)."""
        minutes = set()
        for raw in text.lower().replace(";", ",").replace("\n", ",").split(","):
            s = raw.replace(" ", "").replace(".", "")
            half = None
            for suffix in ("am", "pm"):
                if s.endswith(suffix):
                    half, s = suffix, s[:-2]
            parts = s.split(":")
            if not 1 <= len(parts) <= 3 or not parts[0].isdigit():
                continue
            hour = int(parts[0])
            if len(parts) >= 2:
                if not parts[1].isdigit():
                    continue
                minute = int(parts[1])
            else:
                minute = 0
            if not 0 <= minute < 60:
                continue
            if half:
                if not 1 <= hour <= 12:
                    continue
                hour = hour % 12 + (12 if half == "pm" else 0)
            if 0 <= hour < 24:
                minutes.add(hour * 60 + minute)
        return sorted(minutes)

    @classmethod
    def due(cls, now: datetime) -> bool | None:
        """None if no check-in came due since the last one; else whether it's the day's last."""
        times = cls.times()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        passed = [i for i, t in enumerate(times) if start + timedelta(minutes=t) <= now]
        if not passed:
            return None
        index = passed[-1]
        slot = start + timedelta(minutes=times[index])
        last = settings.get(cls.LAST_KEY)
        if last is not None and datetime.fromtimestamp(float(last)) >= slot:
            return None
        settings.set(cls.LAST_KEY, now.timestamp())
        if now - slot >= cls.LATENESS:
            return None
        return index == len(times) - 1
