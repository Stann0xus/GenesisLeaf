"""Translation pack model, byte-perfect YAML emitter and safe save.

Part of GenesisLeaf 0x01a - see docs/ARCHITECTURE.md.
"""

import hashlib
from contextlib import closing
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
import yaml

from genesisleaf.core.bookkeeping import entry_uuid
from genesisleaf.core.dialog import dialog_boxes
from genesisleaf.core.encoding import parse_text
from genesisleaf.core.space import verdict as space_verdict
from genesisleaf.paths import APP_ROOT
from genesisleaf.diagnostics import current as current_diagnostics
from genesisleaf.core.working_store import WorkingStore


# ---------------------------------------------------------------------------
# SQLite parse cache. YAML remains the interchange and save format. Both the
# editor and comparator call Pack.load, so each loaded file gets its own
# indexed database keyed by path, size and modification time. A cache miss
# parses YAML in a child process for large packs and atomically publishes a DB.
# ---------------------------------------------------------------------------
PARSE_CACHE_KEEP = 8      # newest cached packs kept
PARSE_CACHE_VERSION = 1


def _parse_cache_dir():
    here = os.path.join(APP_ROOT, ".cache", "packs")
    if os.access(APP_ROOT, os.W_OK):
        return here
    return os.path.join(os.path.expanduser("~"), ".genesisleaf", "packs")


def _parse_cache_file(path, st):
    tag = "%d|%s|%d|%d" % (PARSE_CACHE_VERSION,
                           os.path.abspath(path).lower(), st.st_size,
                           st.st_mtime_ns)
    return os.path.join(_parse_cache_dir(),
                        hashlib.sha1(tag.encode("utf-8")).hexdigest()
                        + ".sqlite3")


def _parse_cache_get(path):
    try:
        cf = _parse_cache_file(path, os.stat(path))
        with closing(sqlite3.connect(Path(cf).as_uri() + "?mode=ro",
                                     uri=True)) as db:
            header = json.loads(db.execute(
                "SELECT value FROM metadata WHERE key = 'header'").fetchone()[0])
            names = json.loads(db.execute(
                "SELECT value FROM metadata WHERE key = 'sections'").fetchone()[0])
            sections = {name: [] for name in names}
            for sec, payload in db.execute(
                    "SELECT section, payload FROM entries ORDER BY seq"):
                sections[sec].append(json.loads(payload))
        data = dict(header, sections=sections)
        os.utime(cf)              # recently used: survives pruning
        return data
    except Exception:             # noqa: BLE001 - a miss, never an error
        return None


def _parse_cache_put(path, data):
    tmp = None
    try:
        cf = _parse_cache_file(path, os.stat(path))
        d = os.path.dirname(cf)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(suffix=".sqlite3", dir=d)
        os.close(fd)
        with closing(sqlite3.connect(tmp)) as db:
            db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE entries (seq INTEGER PRIMARY KEY, section TEXT NOT NULL, payload TEXT NOT NULL)")
            db.executemany("INSERT INTO metadata VALUES (?, ?)", (
                ("header", json.dumps({k: v for k, v in data.items() if k != "sections"},
                                       ensure_ascii=False)),
                ("sections", json.dumps(list(data["sections"]), ensure_ascii=False)),
            ))
            db.executemany("INSERT INTO entries (section, payload) VALUES (?, ?)",
                           ((sec, json.dumps(entry, ensure_ascii=False))
                            for sec, entries in data["sections"].items()
                            for entry in (entries or [])))
            db.execute("CREATE INDEX entries_section ON entries(section)")
            db.commit()
        os.replace(tmp, cf)
        old = sorted((os.path.join(d, n) for n in os.listdir(d)
                      if n.endswith(".sqlite3")),
                     key=os.path.getmtime, reverse=True)
        for f in old[PARSE_CACHE_KEEP:]:
            os.remove(f)
    except Exception:             # noqa: BLE001 - caching is optional
        pass
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _parse_yaml_and_cache(path):
    with open(path, "r", encoding="utf-8") as source:
        contents = source.read()
    try:
        data = yaml.load(contents, Loader=yaml.CSafeLoader)
    except Exception:
        data = yaml.safe_load(contents)
    if isinstance(data, dict) and isinstance(data.get("sections"), dict):
        _parse_cache_put(path, data)
    return data


def _parse_in_worker_process(path):
    """Parse a large cache miss outside Tk's Python process.

    PyYAML's C loader can hold the GIL long enough to freeze Tk even when it
    runs in a thread. The child publishes the SQLite cache, so only a short
    cache read and model build happen back in this process.
    """
    if getattr(sys, "frozen", False):
        return None
    monitor = current_diagnostics()
    if monitor is not None:
        monitor.event("YAML_PARSE_PROCESS", file=os.path.basename(path),
                      bytes=os.path.getsize(path))
    try:
        run = subprocess.run(
            [sys.executable, "-m", "genesisleaf.core.parse_cache_worker", path],
            cwd=APP_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False)
        if monitor is not None:
            monitor.event("YAML_PARSE_PROCESS_DONE", exit_code=run.returncode)
        return _parse_cache_get(path) if run.returncode == 0 else None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Pack loading / saving (perfect round-trip, same format as the exporter).
# ---------------------------------------------------------------------------

# pack languages whose text needs the accent font (accented Latin letters)
ACCENT_LANGS = frozenset((
    "pt-br", "pt", "fr", "es", "it", "de", "nl", "pl", "cs", "hu", "ro",
    "sk", "sl", "hr", "sr", "bg", "el", "tr"))


def needs_accent_font(header):
    """Whether a pack with this header previews with the accent font."""
    return str((header or {}).get("language") or "").lower() in ACCENT_LANGS


def scalar(s):
    """Single-quoted scalar like the exporter; falls back to YAML for edge cases."""
    if s is None:
        return "null"
    if isinstance(s, bool):
        return "true" if s else "false"
    if isinstance(s, (int, float)):
        return str(s)
    s = str(s)
    return "'" + s.replace("'", "''") + "'"


class Pack:
    def __init__(self):
        self.path = None
        self.header = {}
        self.sections = {}
        self.section_names = []
        self.flat = []          # list of (section_name, entry_dict)
        self.row_limits = {}    # flat idx -> surface limit, see App.row_limit
        self.same_source = {}   # lower(source) -> [flat indices]
        self.word_index = {}    # word -> [flat indices]
        self._word_cache = {}
        self.working_store = None

    # -- loading ---------------------------------------------------------
    def load(self, path):
        """Read a translation pack from `path`.

        The whole file is parsed and validated into locals first; the pack
        is only touched once everything checked out, so a bad file leaves
        the previous contents intact.  Safe to run on a worker thread for a
        Pack nobody else is reading yet (see ui.app.pack_io)."""
        data = _parse_cache_get(path)
        if data is None:
            # Large files use another process on first open. Threads do not
            # protect the event loop when libyaml keeps the GIL during parse.
            if os.stat(path).st_size >= 1_000_000:
                data = _parse_in_worker_process(path)
            if data is None:
                data = _parse_yaml_and_cache(path)

        if not isinstance(data, dict) or "sections" not in data:
            raise ValueError(
                "This is not a Legend of Legaia translation pack "
                "(missing 'sections').")
        if not isinstance(data["sections"], dict):
            raise ValueError(
                "This is not a valid Legend of Legaia translation pack "
                "('sections' must be a dictionary).")

        sections = {}
        for sec, entries in data["sections"].items():
            if entries is None:
                entries = []
            if not isinstance(entries, list):
                raise ValueError(
                    "Section %r must contain a list of entries." % sec)
            for e in entries:
                if not isinstance(e, dict):
                    raise ValueError("Invalid entry in section %r." % sec)
                e.setdefault("context", "")
                e.setdefault("source", "")
                e.setdefault("translation", "")
                e.setdefault("budget", len(e.get("source", "")))
                # edit bookkeeping (see core.bookkeeping)
                e.setdefault("uuid", entry_uuid(sec, e.get("key", "")))
                e.setdefault("edited", "")
                e.setdefault("joined", "")
            sections[sec] = entries

        header = {k: v for k, v in data.items() if k != "sections"}
        working_store = WorkingStore(path, header, sections)
        if self.working_store is not None:
            self.working_store.close()
        self.working_store = working_store
        self.path = path
        self.header = header
        self.sections = sections
        self.section_names = list(sections)
        self._word_cache = {}
        self.rebuild_indexes()

    def close(self):
        if self.working_store is not None:
            self.working_store.close()
            self.working_store = None

    def rebuild_indexes(self):
        # flat indices are about to be renumbered, so anything cached against
        # them is stale - including each row's on-screen surface
        self.row_limits = {}
        self.flat = []
        for sec in self.section_names:
            for e in self.sections[sec]:
                self.flat.append((sec, e))
        same = {}
        words = {}
        source_words = {}
        for idx, (_, e) in enumerate(self.flat):
            src = e.get("source", "")
            lsrc = src.lower()
            same.setdefault(lsrc, []).append(idx)
            if src not in source_words:
                source_words[src] = self._source_words(src)
            for w in source_words[src]:
                words.setdefault(w, []).append(idx)
        self.same_source = same
        self.word_index = words

    @staticmethod
    def _source_words(src):
        clean = re.sub(r"\{[0-9a-fA-F]{1,2}(?::[0-9a-fA-F]{1,2})?\}", " ", src)
        return set(
            w for w in re.findall(r"[a-z0-9]+", clean.lower())
            if len(w) >= 2
        )

    def words_of(self, idx):
        _, e = self.flat[idx]
        src = e.get("source", "")
        if src not in self._word_cache:
            self._word_cache[src] = sorted(self._source_words(src))
        return self._word_cache[src]

    def dialog_box_map(self):
        """flat index -> (box, row) for `scene_dialog` / `inline_text` lines,
        per the retail pager's box packing (translate_workbench.rs's
        `dialog_boxes`); box numbers continue across the two sections. Lines
        outside those sections are absent. `budget` is the English byte
        length the exporter measured, mirroring the Rust session."""
        m = {}
        next_box = 0
        for sec in self.section_names:
            if sec not in ("scene_dialog", "inline_text"):
                continue
            idxs = [i for i, (s, _e) in enumerate(self.flat) if s == sec]
            if not idxs:
                continue
            lines = []
            for i in idxs:
                e = self.flat[i][1]
                key = e.get("key", "")
                bl = int(e.get("budget", len(e.get("source", ""))))
                lines.append((key, bl))
            boxes = dialog_boxes(lines, next_box)
            if boxes:
                next_box = boxes[-1][0] + 1
            for i, (bx, row) in zip(idxs, boxes):
                m[i] = (bx, row)
        return m

    # -- statistics ------------------------------------------------------
    def stats(self):
        by_sec = {}
        filled = over_budget = non_ascii = over_any = grows = 0
        for sec, e in self.flat:
            d = by_sec.get(sec)
            if d is None:
                d = by_sec[sec] = {"total": 0, "filled": 0,
                                  "over_budget": 0, "non_ascii": 0,
                                  "over_any": 0, "grows": 0}
            d["total"] += 1
            tr = e.get("translation", "")
            if tr:
                d["filled"] += 1
                filled += 1
            b, spans = parse_text(tr)
            # "over" = will not land (a fixed cap, a pinned string, or the
            # measured run refused it); "grows" = longer than its in-place
            # span but its kind grows into free space (core.space)
            v = space_verdict(sec, e, b)
            if v == "over":
                # what the "Won't fit" filter counts (non-ASCII rows too)
                over_any += 1
                d["over_any"] += 1
            if any(st == "nonascii" for _, _, st in spans):
                non_ascii += 1
                d["non_ascii"] += 1
            elif v == "over":
                over_budget += 1
                d["over_budget"] += 1
            elif v == "grows":
                grows += 1
                d["grows"] += 1
        return {
            "by_sec": by_sec,
            "total": len(self.flat),
            "filled": filled,
            "over_budget": over_budget,
            "non_ascii": non_ascii,
            "over_any": over_any,
            "grows": grows,
        }


def emit_pack(pack):
    """Serialise exactly like the exporter writes it (single-quoted, LF)."""
    lines = []
    for k, v in pack.header.items():
        if isinstance(v, list):
            lines.append("%s:" % k)
            for item in v:
                if isinstance(item, dict):
                    inner = ", ".join("%s: %s" % (ik, scalar(iv))
                                      for ik, iv in item.items())
                    lines.append("  - {%s}" % inner)
                else:
                    lines.append("  - %s" % scalar(item))
        elif isinstance(v, dict):
            lines.append("%s:" % k)
            for ik, iv in v.items():
                lines.append("  %s: %s" % (ik, scalar(iv) if not isinstance(iv, (list, dict)) else iv))
        else:
            lines.append("%s: %s" % (k, scalar(v)))
    lines.append("sections:")
    for sec in pack.section_names:
        lines.append("  %s:" % sec)
        for e in pack.sections[sec]:
            entry = dict(e)
            translation = str(entry.get("translation", "")).replace("\r", "").replace("\n", "|")
            lines.append("  - key: %s" % scalar(entry.get("key", "")))
            lines.append("    context: %s" % scalar(entry.get("context", "")))
            lines.append("    source: %s" % scalar(entry.get("source", "")))
            lines.append("    translation: %s" % scalar(translation))
            lines.append("    budget: %s" % int(entry.get("budget", 0)))
            # only when it *pins* the id: load() backfills every row with
            # entry_uuid(sec, key), so persisting the derived value would add
            # ~750 KB of pure redundancy and diverge from the original
            # exporter's output. A hand-set (or older-tool) uuid is kept.
            uu = str(entry.get("uuid", ""))
            if uu and uu != entry_uuid(sec, entry.get("key", "")):
                lines.append("    uuid: %s" % scalar(uu))
            # only when set - 31k always-present `edited: ''` / `joined: ''`
            # lines would add ~1 MB of nothing to every pack
            for extra in ("edited", "joined"):
                v = str(entry.get(extra, "")).replace("\r", "").replace("\n", "|")
                if v:
                    lines.append("    %s: %s" % (extra, scalar(v)))
            # free-form translator notes (the Notes dashboard); kept verbatim,
            # line breaks included
            note = entry.get("notes")
            if note:
                lines.append("    notes: %s" % note_scalar(note))
    return "\n".join(lines) + "\n"


def note_scalar(v):
    """A `notes:` value: single-quoted like every other field, or - when it
    spans lines, which a single-quoted YAML scalar would fold into spaces -
    double-quoted with JSON escapes (a valid YAML double-quoted scalar)."""
    if not isinstance(v, str):
        v = str(v)
    v = v.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" in v or "\t" in v:
        return json.dumps(v, ensure_ascii=False)
    return scalar(v)


def save_pack(pack, path, make_backup=True):
    text = emit_pack(pack)
    utf8 = text.encode("utf-8")
    if make_backup and os.path.exists(path):
        try:
            with open(path, "rb") as f:
                old = f.read()
            if old != utf8:
                with open(path + ".bak", "wb") as f2:
                    f2.write(old)
        except OSError:
            pass
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(utf8)
    os.replace(tmp, path)
    return len(utf8)
