"""Opt-in, low-overhead timings for investigating slow GUI sessions."""

import functools
import os
import queue
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime

from genesisleaf.paths import APP_ROOT


_active = None


def current():
    return _active


def install(root, verbose=False, debug=False):
    global _active
    if not (verbose or debug):
        return None
    _active = Diagnostics(root, debug=debug)
    return _active


class Diagnostics:
    """Write debug records off the Tk thread; sample the loop only while busy."""

    def __init__(self, root, debug=False):
        self.root = root
        self.debug = debug
        self.main_thread = threading.get_ident()
        self.began = time.perf_counter()
        self.counts = Counter()
        self.slow = Counter()
        self.total_ms = Counter()
        self.max_ms = Counter()
        self.frames = 0
        self.preview_frames = 0
        self.lag_max = 0.0
        self.last_activity = self.began
        self.window_start = self.began
        self.tick_job = None
        self.label = None
        self.log_path = None
        self.lines = queue.Queue()
        self.writer = None
        if debug:
            folder = os.path.join(APP_ROOT, "logs")
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                folder = os.path.join(os.path.expanduser("~"), ".genesisleaf", "logs")
                os.makedirs(folder, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            self.log_path = os.path.join(folder, "GenesisLeaf-%s-%d.log" %
                                         (stamp, os.getpid()))
        self.writer = threading.Thread(target=self._write, daemon=True,
                                       name="genesisleaf-log")
        self.writer.start()
        self.event("SESSION", mode="debug" if debug else "verbose",
                   pid=os.getpid())

    def _write(self):
        out = open(self.log_path, "w", encoding="utf-8", buffering=1) \
            if self.debug else None
        console = sys.stdout is not None
        try:
            while True:
                first = self.lines.get()
                if first is None:
                    return
                batch = [first]
                done = False
                for _ in range(63):
                    try:
                        line = self.lines.get_nowait()
                    except queue.Empty:
                        break
                    if line is None:
                        done = True
                        break
                    batch.append(line)
                block = "\n".join(batch) + "\n"
                if out is not None:
                    out.write(block)
                if console:
                    try:
                        sys.stdout.write(block.encode("ascii", "backslashreplace")
                                         .decode("ascii"))
                    except (BrokenPipeError, OSError):
                        console = False
                if done:
                    return
        finally:
            if out is not None:
                out.close()

    def event(self, kind, **fields):
        now = datetime.now().astimezone().isoformat(timespec="microseconds")
        elapsed = (time.perf_counter() - self.began) * 1000
        details = " ".join("%s=%r" % (key, value)
                           for key, value in fields.items())
        self.lines.put("%s +%012.3fms [%s] %s %s" % (
            now, elapsed, threading.current_thread().name, kind, details))

    def attach(self, label):
        self.label = label
        for sequence in ("<KeyPress>", "<ButtonPress>", "<ButtonRelease>",
                         "<B1-Motion>", "<MouseWheel>"):
            self.root.bind_all(sequence, self._input, add="+")
        self.touch()

    def _input(self, evt):
        kind = getattr(evt.type, "name", str(evt.type))
        key = getattr(evt, "keysym", "")
        if len(key) == 1:
            key = "[character]"
        self.event("INPUT", event=kind,
                   widget=str(evt.widget), keysym=key,
                   button=getattr(evt, "num", None),
                   wheel=getattr(evt, "delta", None),
                   modifiers=getattr(evt, "state", None), x=evt.x, y=evt.y)
        self.touch()
        if kind in ("MouseWheel", "Motion"):
            self._probe_loop("input." + kind)

    def touch(self):
        if threading.get_ident() != self.main_thread:
            return
        self.last_activity = time.perf_counter()
        if self.tick_job is None:
            self.window_start = self.last_activity
            self.frames = 0
            self.lag_max = 0.0
            self.tick_job = self.root.after(16, self._tick,
                                            self.last_activity + 0.016)

    def _tick(self, expected):
        self.tick_job = None
        now = time.perf_counter()
        self.frames += 1
        self.lag_max = max(self.lag_max, max(0.0, now - expected) * 1000)
        span = now - self.window_start
        if span >= 1.0:
            fps = self.frames / span
            msg = ("UI %.0f fps | lag max %.0f ms | previews %d | "
                   "ops %d | slow %d" %
                   (fps, self.lag_max, self.preview_frames,
                    sum(self.counts.values()), sum(self.slow.values())))
            if self.label is not None:
                try:
                    self.label.configure(text=msg)
                except Exception:
                    pass
            self.event("UI_SAMPLE", fps=round(fps, 1), lag_max_ms=round(self.lag_max, 2),
                       preview_frames=self.preview_frames, operations=sum(self.counts.values()),
                       slow_operations=sum(self.slow.values()))
            self.window_start = now
            self.frames = 0
            self.preview_frames = 0
            self.lag_max = 0.0
        if now - self.last_activity < 2.0:
            self.tick_job = self.root.after(16, self._tick, now + 0.016)
        elif self.label is not None:
            try:
                self.label.configure(text="UI idle | ops %d | slow %d" %
                                     (sum(self.counts.values()), sum(self.slow.values())))
            except Exception:
                pass

    def record(self, name, elapsed_ms, failed=False):
        self.counts[name] += 1
        self.total_ms[name] += elapsed_ms
        self.max_ms[name] = max(self.max_ms[name], elapsed_ms)
        if elapsed_ms >= 16:
            self.slow[name] += 1
            self.event("SLOW", operation=name, duration_ms=round(elapsed_ms, 3),
                       failed=failed)
        if name.endswith("render_text_to_canvas") and not failed:
            self.preview_frames += 1
        if threading.get_ident() == self.main_thread and (
                elapsed_ms >= 4 or name.endswith(("._load_poll", "._cmp_poll"))):
            self.touch()
        if threading.get_ident() == self.main_thread and name in (
                "App._on_rowkey", "App._cmp_on_select"):
            self._probe_loop(name)

    def _probe_loop(self, name):
        started = time.perf_counter()

        def returned():
            self.event("EVENT_LOOP_RETURN", operation=name,
                       wait_ms=round((time.perf_counter() - started) * 1000, 3))

        def idle():
            self.event("IDLE_REACHED", operation=name,
                       wait_ms=round((time.perf_counter() - started) * 1000, 3))

        try:
            self.root.after(0, returned)
            self.root.after_idle(idle)
        except Exception:
            pass

    @contextmanager
    def span(self, name, **fields):
        self.touch()
        self.event("BEGIN", operation=name, **fields)
        start = time.perf_counter()
        failed = False
        try:
            yield
        except BaseException as exc:
            failed = True
            self.event("ERROR", operation=name, exception=type(exc).__name__)
            raise
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            self.event("END", operation=name, duration_ms=round(elapsed, 3),
                       failed=failed)
            self.record(name, elapsed, failed)

    def close(self):
        if self.tick_job is not None:
            try:
                self.root.after_cancel(self.tick_job)
            except Exception:
                pass
            self.tick_job = None
        for name, _count in self.total_ms.most_common(20):
            self.event("SUMMARY", operation=name, calls=self.counts[name],
                       total_ms=round(self.total_ms[name], 3),
                       max_ms=round(self.max_ms[name], 3))
        self.event("SESSION_END")
        self.lines.put(None)
        self.writer.join()


def traced(name=None):
    """Trace one meaningful operation, preserving exceptions and results."""
    def decorate(fn):
        operation = name or (fn.__module__ + "." + fn.__qualname__)

        @functools.wraps(fn)
        def call(*args, **kwargs):
            monitor = current()
            if monitor is None:
                return fn(*args, **kwargs)
            monitor.touch()
            monitor.event("BEGIN", operation=operation,
                          **_operation_context(operation, args, kwargs))
            start = time.perf_counter()
            failed = False
            try:
                return fn(*args, **kwargs)
            except BaseException as exc:
                failed = True
                monitor.event("ERROR", operation=operation,
                              exception=type(exc).__name__)
                raise
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                monitor.event("END", operation=operation,
                              duration_ms=round(elapsed, 3), failed=failed)
                monitor.record(operation, elapsed, failed)

        return call
    return decorate


def _operation_context(operation, args, kwargs):
    """Useful identifiers for traces, without including translation text."""
    method = operation.rsplit(".", 1)[-1]
    try:
        if method in ("load", "load_pack", "_load_pack_async"):
            path = args[1] if len(args) > 1 else kwargs.get("path")
            return {"file": os.path.basename(path)} if path else {}
        if method in ("select_entry", "_cmp_follow_main"):
            return {"row": args[1] if len(args) > 1 else kwargs.get("index")}
        if method in ("_insert_plan", "_insert_cmp_rows", "_insert_rows"):
            return {"start": args[1] if len(args) > 1 else None}
        if method == "_on_rowkey":
            return {"key": getattr(args[1], "keysym", "")} if len(args) > 1 else {}
        if method == "_cmp_on_select":
            return {"side": args[1] if len(args) > 1 else None}
        if method in ("render_font_rows", "render_text_to_canvas"):
            rows = args[0] if method == "render_font_rows" else args[1]
            return {"rows": len(rows)}
        if method == "request" and len(args) > 2:
            return {"canvas": str(args[1]), "rows": len(args[2])}
    except (IndexError, TypeError, AttributeError):
        pass
    return {}


def trace_methods(cls, names):
    """Instrument inherited App methods before callbacks bind to them."""
    for name in names:
        method = getattr(cls, name, None)
        if method is not None and not getattr(method, "_genesisleaf_traced", False):
            wrapped = traced(cls.__name__ + "." + name)(method)
            wrapped._genesisleaf_traced = True
            setattr(cls, name, wrapped)
