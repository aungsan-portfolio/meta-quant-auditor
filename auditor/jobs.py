"""Keep optional model work off the deterministic audit calculation path."""
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Callable

from .audit import AuditTrace, Finding
from .model import Explanation, explain


class ExplanationJob:
    def __init__(self, worker: Callable = explain):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='synthetic-explanation')
        self._lock = Lock()
        self._worker = worker
        self._future: Future | None = None
        self._identity: tuple[str, str] | None = None

    def start(self, trace: AuditTrace, finding: Finding, key: str) -> bool:
        with self._lock:
            if self._future is not None and not self._future.done():
                return False
            self._identity = (getattr(trace, 'job_identity', trace.trace_id), finding.event_id)
            self._future = self._executor.submit(self._worker, trace, finding, key)
            return True

    def state(self, trace: AuditTrace, finding: Finding) -> tuple[str, Explanation | None]:
        with self._lock:
            identity = (getattr(trace, 'job_identity', trace.trace_id), finding.event_id)
            if self._future is None:
                return 'NOT_STARTED', None
            if not self._future.done():
                return ('PENDING' if self._identity == identity else 'OTHER_PENDING'), None
            if self._identity != identity:
                return 'NOT_STARTED', None
            try:
                result = self._future.result()
                return ('DONE', result) if isinstance(result, Explanation) else ('DONE', Explanation('UNAVAILABLE', 'MODEL_UNAVAILABLE'))
            except Exception:
                return 'DONE', Explanation('UNAVAILABLE', 'MODEL_UNAVAILABLE')

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
