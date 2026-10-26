"""
File · src/awp/proc.py
Purpose · The one way to run a long-lived child process (a browser, a server, an agent) under a hard deadline, so the method (every command carries a timeout; no background process left behind) holds for processes that subprocess.run cannot express.
Description · Child wraps subprocess.Popen with a watchdog timer that terminates, then kills, the process at the deadline, and a context manager that stops it on exit. the checks (check timeouts) forbids Popen everywhere except this file. Shaped by the E0 pilot of 2026-10-18: reading Chromium's accessibility tree needs a live DevTools pipe, which a one-shot run cannot provide.
Inputs/Outputs · In: argv, deadline in seconds, optional pass_fds, env, cwd, stdout, stderr (fd renumbering is done by the caller through a shell exec, never by preexec_fn). Out: a running process handle with .stop(); .timed_out set if the watchdog fired.
Depends on · subprocess, threading.
Invariant · No Child outlives its deadline or its with-block; stop() is idempotent.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading


class Child:
    def __init__(self, argv, deadline_s, *, pass_fds=(), env=None, cwd=None, stdout=None, stderr=None):
        self.argv = list(argv)
        self.deadline_s = float(deadline_s)
        self.timed_out = False
        self._lock = threading.Lock()
        self.proc = subprocess.Popen(self.argv, pass_fds=pass_fds, env=env, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True)
        self._timer = threading.Timer(self.deadline_s, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def _expire(self):
        self.timed_out = True
        self.stop()

    def stop(self, grace_s=3.0):
        with self._lock:
            self._timer.cancel()
            if self.proc.poll() is not None:
                return
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=grace_s)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.proc.wait(timeout=grace_s)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
        return False
