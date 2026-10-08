"""SQLite working copy of a loaded YAML pack.

The model keeps its existing mutable dictionaries for fast editor access. Each
change is also coalesced into the indexed SQLite database on a writer thread,
so typing never waits for a disk commit.
"""

import json
import os
import sqlite3
import tempfile
import threading
import time

from genesisleaf.paths import APP_ROOT
from genesisleaf.diagnostics import current as current_diagnostics


class TrackedEntry(dict):
    def __init__(self, values, store, sequence):
        super().__init__(values)
        self._store = store
        self._sequence = sequence

    def _changed(self):
        self._store.changed(self._sequence)

    def __setitem__(self, key, value):
        if self.get(key) != value or key not in self:
            super().__setitem__(key, value)
            self._changed()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._changed()

    def update(self, *args, **kw):
        values = dict(*args, **kw)
        if any(self.get(k) != v or k not in self for k, v in values.items()):
            super().update(values)
            self._changed()

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def pop(self, key, *default):
        if key in self:
            value = super().pop(key)
            self._changed()
            return value
        if default:
            return default[0]
        raise KeyError(key)

    def clear(self):
        if self:
            super().clear()
            self._changed()


class WorkingStore:
    """Owns one indexed database and a batched writer for one loaded pack."""

    def __init__(self, source, header, sections):
        folder = os.path.join(APP_ROOT, ".cache", "work")
        try:
            os.makedirs(folder, exist_ok=True)
            fd, self.path = tempfile.mkstemp(prefix="pack-%d-" % os.getpid(), suffix=".sqlite3",
                                              dir=folder)
        except OSError:
            folder = os.path.join(tempfile.gettempdir(), "genesisleaf-work")
            os.makedirs(folder, exist_ok=True)
            fd, self.path = tempfile.mkstemp(prefix="pack-%d-" % os.getpid(), suffix=".sqlite3",
                                              dir=folder)
        os.close(fd)
        self.entries = {}
        self._pending = set()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._closed = False
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA synchronous=NORMAL")
            db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE entries (seq INTEGER PRIMARY KEY, "
                       "section TEXT NOT NULL, key TEXT, source TEXT, "
                       "translation TEXT, payload TEXT NOT NULL)")
            db.executemany("INSERT INTO metadata VALUES (?, ?)", (
                ("source", os.path.abspath(source)),
                ("header", json.dumps(header, ensure_ascii=False, default=str)),
                ("sections", json.dumps(list(sections), ensure_ascii=False)),
            ))
            def records():
                seq = 0
                for section, rows in sections.items():
                    for entry in rows:
                        yield (seq, section, str(entry.get("key", "")),
                               str(entry.get("source", "")),
                               str(entry.get("translation", "")),
                               json.dumps(entry, ensure_ascii=False, default=str))
                        seq += 1

            db.executemany("INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?)", records())
            db.execute("CREATE INDEX entries_section ON entries(section, seq)")
            db.execute("CREATE INDEX entries_key ON entries(key)")
            db.execute("CREATE INDEX entries_source ON entries(source)")
            db.commit()
        seq = 0
        for section, rows in sections.items():
            for pos, entry in enumerate(rows):
                tracked = TrackedEntry(entry, self, seq)
                rows[pos] = tracked
                self.entries[seq] = tracked
                seq += 1
        monitor = current_diagnostics()
        if monitor is not None:
            monitor.event("WORK_DB_READY", file=os.path.basename(source),
                          rows=seq, database=self.path)
        self._writer = threading.Thread(target=self._write, daemon=True,
                                        name="genesisleaf-sqlite")
        self._writer.start()

    def changed(self, sequence):
        with self._lock:
            if self._closed:
                return
            self._pending.add(sequence)
        self._wake.set()

    def _write(self):
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA synchronous=NORMAL")
            while True:
                self._wake.wait()
                self._wake.clear()
                if not self._closed:
                    time.sleep(0.04)  # collect a burst of keystrokes
                with self._lock:
                    pending = self._pending
                    self._pending = set()
                    done = self._closed
                if pending:
                    rows = []
                    for seq in pending:
                        entry = self.entries.get(seq)
                        if entry is not None:
                            snapshot = dict(entry)
                            rows.append((str(snapshot.get("translation", "")),
                                         json.dumps(snapshot, ensure_ascii=False,
                                                    default=str), seq))
                    db.executemany("UPDATE entries SET translation=?, payload=? WHERE seq=?",
                                   rows)
                    db.commit()
                    monitor = current_diagnostics()
                    if monitor is not None:
                        monitor.event("WORK_DB_FLUSH", rows=len(rows))
                if done:
                    return

    def close(self):
        with self._lock:
            self._closed = True
        self._wake.set()
        self._writer.join(timeout=2)
        self.entries.clear()
        if not self._writer.is_alive():
            try:
                os.remove(self.path)
            except OSError:
                pass
