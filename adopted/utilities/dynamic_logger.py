# coding: utf-8
"""Level-tagged logging with a bounded history, adopted from Kali.

    kali:UTILITIES/AzazaelDynamicLogger.py#DynamicLogger -> DynamicLogger
    kali:UTILITIES/AzazaelDynamicLogger.py#LogLevel      -> LogLevel

The Kali module is a singleton that starts a daemon writer thread at
construction and appends to `logs/azazael_dynamic.log` beside itself. That is a
defensible CLI behaviour and a poor library one: importing a logger should not
create a thread, and a library should not decide where a file goes.

So the adoption keeps the surface -- `log`, `debug`, `info`, `warn`, `error`,
`success`, a `deque(maxlen=1000)` history, the five level names -- and makes the
two side effects explicit:

* no thread. `log()` appends to the history and, if a sink was given, appends
  one line to it. A caller that wants asynchronous writing can hand in its own.
* no default file. `DynamicLogger(sink=Path(...))` opts in; with no sink nothing
  touches the disk.

`get_logger()` is the singleton accessor. `DynamicLogger()` is still a singleton
per process, as in the source, so a second call returns the same object.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Optional


class LogLevel:
    """The five names the source uses. Strings, not an enum, on purpose."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"

    ALL = (DEBUG, INFO, WARN, ERROR, SUCCESS)


_SYMBOLS = {
    LogLevel.DEBUG: "[?]",
    LogLevel.INFO: "[+]",
    LogLevel.WARN: "[!]",
    LogLevel.ERROR: "[-]",
    LogLevel.SUCCESS: "[*]",
}


class DynamicLogger:
    """One logger per process; history always, output and file by choice."""

    _instance: Optional["DynamicLogger"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._ready = False
        return cls._instance

    def __init__(self, sink: Optional[Path] = None, history: int = 1000) -> None:
        if self._ready:
            if sink is not None:
                self.sink = Path(sink)
            return
        self._ready = True
        self.history: Deque[Dict[str, str]] = deque(maxlen=history)
        self.sink = Path(sink) if sink is not None else None
        self.quiet = False
        self.output_enabled = True
        self._lock = threading.Lock()

    def log(self, message: str, level: str = LogLevel.INFO, tag: str = "") -> Dict[str, str]:
        """Record one line. Returns the record, so a caller can assert on it."""
        timestamp = datetime.now().isoformat()
        text = ("%s %s" % (tag, message)).strip() if tag else message
        record = {"ts": timestamp, "lvl": level, "msg": text}
        if self.quiet:
            return record
        with self._lock:
            self.history.append(record)
            if self.output_enabled:
                print("%s %s %s" % (_SYMBOLS.get(level, "[?]"), timestamp[11:19], text),
                      flush=True)
            if self.sink is not None:
                self.sink.parent.mkdir(parents=True, exist_ok=True)
                with self.sink.open("a", encoding="utf-8") as handle:
                    handle.write("%s | %-7s | %s\n" % (timestamp, level, text))
        return record

    def debug(self, message: str, tag: str = "") -> Dict[str, str]:
        return self.log(message, LogLevel.DEBUG, tag)

    def info(self, message: str, tag: str = "") -> Dict[str, str]:
        return self.log(message, LogLevel.INFO, tag)

    def warn(self, message: str, tag: str = "") -> Dict[str, str]:
        return self.log(message, LogLevel.WARN, tag)

    def error(self, message: str, tag: str = "") -> Dict[str, str]:
        return self.log(message, LogLevel.ERROR, tag)

    def success(self, message: str, tag: str = "") -> Dict[str, str]:
        return self.log(message, LogLevel.SUCCESS, tag)

    def clear(self) -> None:
        with self._lock:
            self.history.clear()


def get_logger(**kwargs) -> DynamicLogger:
    """The process-wide logger. Configuration is honoured on first call only."""
    return DynamicLogger(**kwargs)
