"""Optional whole-replay explanation; deterministic results stay authoritative."""
from __future__ import annotations

import json
from typing import NamedTuple

from .model import ENDPOINT, MODEL, Explanation, TransportError, _post
from .workbench import Replay, report_evidence


class WholeReplay(NamedTuple):
    # The existing background job uses a stable event ID to avoid stale output.
    event_id: str = 'WHOLE_REPLAY'


SYSTEM = (
    'Explain the supplied synthetic paper-simulation audit for a human reviewer. '
    'Use only the supplied facts, identify each blocker or veto and cite its event ID, '
    'and distinguish individual gates from the overall simulated decision. '
    'If a limit is unknown say so. Do not invent data, issue trade recommendations, '
    'claim a real order occurred, or change a decision. State that the data is synthetic.'
)


def explain_replay(report: Replay, _selection: WholeReplay, api_key: str, *, transport=_post) -> Explanation:
    if not isinstance(report, Replay):
        return Explanation('UNAVAILABLE', 'INVALID_EVIDENCE')
    return _explain(SYSTEM, report_evidence(report), api_key, transport)


def explain_recorded_review(review, _selection: WholeReplay, api_key: str, *, transport=_post) -> Explanation:
    from .trace_review import TraceReview, review_evidence
    if not isinstance(review, TraceReview):
        return Explanation('UNAVAILABLE', 'INVALID_EVIDENCE')
    system = (SYSTEM + ' Also explain any deterministic MISMATCH or INCOMPLETE checks. '
              'Do not claim a consistency check proves a real-world event occurred.')
    return _explain(system, review_evidence(review), api_key, transport)


def _explain(system: str, evidence: dict, api_key: str, transport) -> Explanation:
    if not isinstance(api_key, str) or not api_key.strip() or api_key.strip() == 'your_baseten_api_key_here':
        return Explanation('UNAVAILABLE', 'KEY_MISSING')
    body = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(evidence, sort_keys=True, allow_nan=False)},
        ],
        'max_tokens': 1536,
        'reasoning_effort': 'low',
        'stream': False,
    }
    try:
        response = transport(ENDPOINT, api_key.strip(), body, 30.0)
        choice = response['choices'][0]
        finish = choice.get('finish_reason')
        if finish == 'length':
            return Explanation('UNAVAILABLE', 'OUTPUT_TRUNCATED')
        if finish != 'stop':
            return Explanation('UNAVAILABLE', 'OUTPUT_INCOMPLETE')
        answer = choice['message']['content']
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 12000:
            return Explanation('UNAVAILABLE', 'INVALID_RESPONSE')
        return Explanation('AVAILABLE', 'MODEL_EXPLANATION', answer.strip())
    except TransportError as exc:
        allowed = {'RESPONSE_TOO_LARGE', 'ACCESS_DENIED', 'RATE_LIMITED', 'HTTP_ERROR',
                   'TIMEOUT', 'CONNECTION_ERROR', 'INVALID_RESPONSE'}
        return Explanation('UNAVAILABLE', str(exc) if str(exc) in allowed else 'MODEL_UNAVAILABLE')
    except (KeyError, IndexError, TypeError, AttributeError):
        return Explanation('UNAVAILABLE', 'INVALID_RESPONSE')
    except Exception:
        return Explanation('UNAVAILABLE', 'MODEL_UNAVAILABLE')
