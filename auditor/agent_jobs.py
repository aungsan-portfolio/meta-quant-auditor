"""One background run per UI session; snapshots contain no API key."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, Lock

from .agent import AgentRun
from . import agent_model


class AgentJob:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='synthetic-auditor-agent')
        self._lock = Lock()
        self._future = None
        self._snapshot = None
        self._cancel = Event()

    def _publish(self, value):
        with self._lock:
            self._snapshot = deepcopy(value)

    def start(self, scenario_id: str, api_key: str, *, consent: bool) -> bool:
        if consent is not True or not isinstance(api_key, str) or not api_key.strip() or api_key.strip() == 'your_baseten_api_key_here':
            return False
        with self._lock:
            if self._future is not None and not self._future.done():
                return False
            run = AgentRun(scenario_id)
            self._cancel = Event()
            self._snapshot = run.snapshot()
            # Key exists only in this worker closure; never in the snapshot/context.
            self._future = self._executor.submit(
                run.run, lambda ctx: agent_model.request_action_observed(ctx, api_key.strip()),
                on_update=self._publish, cancelled=self._cancel.is_set)
            return True

    def snapshot(self):
        with self._lock:
            value = deepcopy(self._snapshot)
            busy = self._future is not None and not self._future.done()
        return busy, value

    def stop(self):
        self._cancel.set()

    def close(self):
        self.stop()
        self._executor.shutdown(wait=True, cancel_futures=True)
