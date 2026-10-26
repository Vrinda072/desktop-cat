"""Her preset lines, the reminders, and what she reads from the messages sheet."""
import json
import random
import sys
import threading
import time
import urllib.parse
import urllib.request

from PySide6.QtCore import QObject, Signal

from . import resources
from .resources import config, settings
from .todos import CheckIns

CACHE = resources.DATA_FOLDER / "messages.json"


def log(text):
    print(f"DesktopCat: {text}", file=sys.stderr)


# MARK: - Parsing

def csv_rows(text: str) -> list[list[str]]:
    """Every CSV row's fields, handling quoted fields with commas, quotes and line breaks."""
    rows, row, field, in_quotes = [], [], "", False
    text = text.replace("\r\n", "\n").lstrip("﻿")
    i = 0
    while i < len(text):
        c = text[i]
        if in_quotes:
            if c == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    field += '"'
                    i += 1
                else:
                    in_quotes = False
            else:
                field += c
        elif c == '"':
            in_quotes = True
        elif c == ",":
            row.append(field)
            field = ""
        elif c in "\n\r":
            row.append(field)
            rows.append(row)
            row, field = [], ""
        else:
            field += c
        i += 1
    if field or row:
        row.append(field)
        rows.append(row)
    return rows


def _looks_like_html(text: str) -> bool:
    """Google answers with a sign-in page when a file isn't shared; that's not a list of messages."""
    start = text[:200].lower()
    return "<!doctype html" in start or "<html" in start


def parse_messages(data: bytes) -> list[str]:
    """Accepts messages.json (categories of lines) or a CSV export of a sheet (first column, one
    message per row; a first row that just says "message" or "messages" is a header)."""
    lines: list[str] = []
    try:
        groups = json.loads(data.decode("utf-8-sig"))
        if isinstance(groups, dict):
            for key in sorted(groups):
                if isinstance(groups[key], list):
                    lines += [str(x) for x in groups[key]]
    except (ValueError, UnicodeDecodeError):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return []
        if _looks_like_html(text) or text.strip().startswith("{"):   # a sign-in page or broken JSON
            return []
        lines = [row[0] if row else "" for row in csv_rows(text)]
        if lines and lines[0].strip().lower() in ("message", "messages"):
            lines.pop(0)
    return [line.strip() for line in lines if line.strip()]


class Messages:
    """Picks preset lines without repeating recent ones. The newest online copy wins over the
    built-in one."""

    def __init__(self):
        self._all: list[str] = []
        self._recent: list[str] = []
        try:
            if self.load(CACHE.read_bytes()):
                return
        except OSError:
            pass
        try:
            if not self.load(resources.url("messages.json").read_bytes()):
                log("messages.json has no messages")
        except OSError as error:
            log(f"could not read messages.json: {error}")

    def load(self, data: bytes) -> bool:
        """Returns False (and keeps the current lines) if the data is broken or empty."""
        lines = parse_messages(data)
        if not lines:
            return False
        self._all = lines
        return True

    def next(self) -> str | None:
        if not self._all:
            return None
        # Avoid the last few lines (up to half the list) so nothing repeats soon.
        avoid = min(len(self._all) // 2, 5)
        recent = self._recent[-avoid:] if avoid else []
        pool = [m for m in self._all if m not in recent] or self._all
        pick = random.choice(pool)
        self._recent = (self._recent + [pick])[-10:]
        return pick


class Reminders:
    """Periodic reminders from reminders.json, each on its own interval."""

    def __init__(self):
        try:
            raw = json.loads(resources.url("reminders.json").read_text(encoding="utf-8"))
            self.items = [r for r in raw if float(r.get("everyMinutes", 0)) > 0]
        except (OSError, ValueError) as error:
            log(f"could not read reminders.json: {error}")
            self.items = []
        self._next_due: list[float] = []

    def restart(self):
        now = time.time()
        self._next_due = [now + float(r["everyMinutes"]) * 60 for r in self.items]

    def due(self, now: float) -> dict | None:
        """At most one fires at a time; others that are also due wait a couple of minutes."""
        index = next((i for i, t in enumerate(self._next_due) if t <= now), None)
        if index is None:
            return None
        self._next_due[index] = now + float(self.items[index]["everyMinutes"]) * 60
        for other, t in enumerate(self._next_due):
            if other != index and t <= now + 120:
                self._next_due[other] = now + 120
        return self.items[index]


# MARK: - Fetching

class _Bridge(QObject):
    """Hands a background download's result back to the UI thread."""
    done = Signal(object, object)

    def __init__(self):
        super().__init__()
        self.done.connect(lambda callback, value: callback(value))


_bridge = None


def fetch(url: str, callback):
    """Downloads `url` on a background thread, then calls callback(bytes or None) on the UI thread."""
    global _bridge
    if _bridge is None:
        _bridge = _Bridge()
    bridge = _bridge

    def work():
        data = None
        try:
            request = urllib.request.Request(url, headers={"Cache-Control": "no-cache",
                                                           "User-Agent": "DesktopCat"})
            with urllib.request.urlopen(request, timeout=30) as response:
                if getattr(response, "status", None) in (200, None):   # None: a local file
                    data = response.read()
        except Exception as error:   # offline, bad link, ...
            log(f"could not fetch {url.split('?')[0]}: {error}")
        bridge.done.emit(callback, data)

    threading.Thread(target=work, daemon=True).start()


def sheet_parts(link: str):
    """(host, path parts, query dict, fragment) of a share link."""
    parsed = urllib.parse.urlparse(link)
    parts = [p for p in parsed.path.split("/") if p]
    return parsed.hostname or "", parts, urllib.parse.parse_qs(parsed.query), parsed.fragment


def download_url(link: str) -> str:
    """Turns a Google Sheets or Drive share link into a link that downloads the contents."""
    host, parts, query, fragment = sheet_parts(link)
    if "d" not in parts or parts.index("d") + 1 >= len(parts):
        return link
    file_id = parts[parts.index("d") + 1]
    if host == "docs.google.com" and "spreadsheets" in parts:
        csv = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv"
        gid = (query.get("gid") or [None])[0] or (fragment[4:] if fragment.startswith("gid=") else "")
        if gid:
            csv += f"&gid={gid}"
        return csv
    if host == "drive.google.com" and "file" in parts:
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return link


class RemoteMessages:
    """Fetches the messages (the controller asks every minute) from the messages sheet: the link
    built in from config.json, or one pasted from the tray menu. Without a link she sticks to her
    built-in messages. The last good copy is cached."""

    def __init__(self, messages: Messages):
        self.messages = messages

    @staticmethod
    def link() -> str:
        saved = settings.get("messagesLink")
        return (saved if saved is not None else config.get("messagesLink") or "").strip()

    @classmethod
    def source(cls) -> str | None:
        link = cls.link()
        return download_url(link) if link.startswith("https://") else None

    def set_link(self, text: str) -> bool:
        trimmed = text.strip()
        if trimmed and not trimmed.startswith("https://"):
            return False
        settings.set("messagesLink", trimmed)
        self.refresh()
        return True

    def refresh(self):
        source = self.source()
        if source:
            fetch(source, self._received)

    def _received(self, data):
        if data is None:
            return
        # A broken or empty file (or a sign-in page) must not wipe out her messages.
        if not self.messages.load(data):
            log("the online messages are broken, empty or not shared; keeping the current messages")
            return
        try:
            resources.write_atomic(CACHE, data)
        except OSError as error:
            log(f"could not cache messages: {error}")


class RemoteControl:
    """Reads the "Control" tab of the messages sheet: Nudge, Check-in times and (new on Windows)
    From, the name a nudge is signed with."""

    TAB = "Control"

    def __init__(self, on_nudge):
        self.on_nudge = on_nudge

    @classmethod
    def source(cls) -> str | None:
        feed = settings.get("controlFeed")   # for tests: a file:// URL
        if feed:
            return feed
        host, parts, _, _ = sheet_parts(RemoteMessages.link())
        if host != "docs.google.com" or "spreadsheets" not in parts or "d" not in parts:
            return None
        d = parts.index("d")
        if d + 1 >= len(parts):
            return None
        query = urllib.parse.urlencode({"tqx": "out:csv", "headers": "0", "sheet": cls.TAB})
        return f"https://docs.google.com/spreadsheets/d/{parts[d + 1]}/gviz/tq?{query}"

    def refresh(self):
        source = self.source()
        if source:
            fetch(source, self._received)

    @staticmethod
    def parse(text: str) -> dict:
        """Picks the named rows out of the tab. Without a Control tab Google sends the first tab,
        which has none of them, so nothing changes."""
        found = {}
        if "<html" in text[:200].lower():
            return found
        for row in csv_rows(text):
            if len(row) < 2:
                continue
            name, value = row[0].strip().lower(), row[1].strip()
            if name == "nudge":
                found["nudge"] = value
            elif name.startswith(("check-in", "check in", "checkin")):
                found["times"] = value
            elif name == "from":
                found["from"] = value
        return found

    def _received(self, data):
        if data is None:
            return
        try:
            control = self.parse(data.decode("utf-8"))
        except UnicodeDecodeError:
            return
        if "times" in control:
            if CheckIns.parse(control["times"]):
                settings.set(CheckIns.TIMES_KEY, control["times"])
            else:
                settings.remove(CheckIns.TIMES_KEY)
        if "from" in control:
            settings.set("nudgeFrom", control["from"] or None)
        nudge = control.get("nudge")
        if nudge and nudge != settings.get("lastNudge"):
            settings.set("lastNudge", nudge)
            self.on_nudge(nudge)


class LiveMessages:
    """Reads the "Live" tab of the messages sheet every few seconds, so a line typed there shows
    up on his screen right away.

    The tab's first cell must start with "Live" (e.g. "Live messages"); Google sends the first tab
    instead when there's no Live tab, and that must not be mistaken for live messages. Every
    non-empty row under it is a message. A new row, or a change to the last one, is shown; the
    rows already there when the cat first reads the tab are not, so she doesn't replay old ones.
    """

    TAB = "Live"
    COUNT_KEY = "liveCount"
    LAST_KEY = "liveLast"

    def __init__(self, on_message):
        self.on_message = on_message
        self._busy = False

    @classmethod
    def source(cls) -> str | None:
        feed = settings.get("liveFeed")   # for tests: a file:// URL
        if feed:
            return feed
        control = RemoteControl.source()
        if not control or "gviz" not in control:
            return None
        return control.replace(f"sheet={RemoteControl.TAB}", f"sheet={cls.TAB}")

    def refresh(self):
        source = self.source()
        if source and not self._busy:
            self._busy = True
            fetch(source, self._received)

    @classmethod
    def parse(cls, text: str) -> list[str] | None:
        """The messages in the tab, or None if this isn't the Live tab."""
        if "<html" in text[:200].lower():
            return None
        rows = [row[0].strip() if row else "" for row in csv_rows(text)]
        if not rows or not rows[0].lower().startswith("live"):
            return None
        return [r for r in rows[1:] if r]

    def _received(self, data):
        self._busy = False
        if data is None:
            return
        try:
            lines = self.parse(data.decode("utf-8"))
        except UnicodeDecodeError:
            return
        if lines is None:
            return
        count, last = settings.get(self.COUNT_KEY), settings.get(self.LAST_KEY)
        settings.set(self.COUNT_KEY, len(lines))
        settings.set(self.LAST_KEY, lines[-1] if lines else "")
        if count is None:
            return   # first look at the tab: what's there is old news
        if len(lines) > count:
            new = lines[count:]
        elif lines and len(lines) == count and lines[-1] != last:
            new = [lines[-1]]   # she edited her last line
        else:
            return   # nothing new (or rows were deleted)
        self.on_message("\n".join(new))
