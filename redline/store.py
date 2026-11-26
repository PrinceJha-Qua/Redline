"""Open a Redline store read-only and run queries on it.

Relate connections belong to the thread that opened them, so a web server or MCP server hands
every query to one worker thread that owns the connection.

`hypothetical` runs a function inside a transaction on that read-only connection: Relate accepts the
writes, answers queries against them, and refuses to commit them. Redline rolls back every time, so a
what-if ("overrule this case, then check the brief") uses the production code and leaves the store
untouched.
"""
import atexit
import os
import queue
import threading
from concurrent.futures import Future
from pathlib import Path

import relate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = ROOT / "data" / "redline-us"


def store_path():
    return Path(os.getenv("REDLINE_STORE") or DEFAULT_STORE)


def _plain(value):
    if isinstance(value, relate.Node):
        return dict(value.properties)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else store_path()
        if not self.path.exists():
            raise FileNotFoundError(f"No Redline store at {self.path}. Run `make data` to build it.")
        self._jobs = queue.Queue()
        ready = Future()
        self._thread = threading.Thread(target=self._work, args=(ready,), daemon=True, name="redline-store")
        self._thread.start()
        ready.result()
        atexit.register(self.close)

    def _work(self, ready):
        try:
            con = relate.connect(str(self.path), read_only=True)
        except Exception as e:  # surface the open error to the caller
            ready.set_exception(e)
            return
        ready.set_result(True)
        self._con, self._cur = con, con.cursor()
        while True:
            job = self._jobs.get()
            if job is None:
                con.close()
                return
            fut, fn = job
            try:
                fut.set_result(fn())
            except Exception as e:
                fut.set_exception(e)

    def _run(self, query, params=None):
        self._cur.execute(query, params or {})
        return [{k: _plain(v) for k, v in dict(r).items()} for r in self._cur.fetchall()]

    def _submit(self, fn):
        if threading.current_thread() is self._thread:  # already on the worker: inside `hypothetical`
            return fn()
        fut = Future()
        self._jobs.put((fut, fn))
        return fut.result()

    def query(self, query, params=None):
        return self._submit(lambda: self._run(query, params))

    def hypothetical(self, writes, fn):
        """Apply `writes` (a list of (cypher, params)) inside a transaction, return fn(), then roll back."""
        def job():
            self._con.autocommit = False
            try:
                for q, p in writes:
                    self._run(q, p)
                return fn()
            finally:
                self._con.rollback()
                self._con.autocommit = True
        return self._submit(job)

    def close(self):
        if self._thread.is_alive():
            self._jobs.put(None)
            self._thread.join(timeout=5)
