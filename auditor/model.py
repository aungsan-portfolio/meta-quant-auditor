"""Optional one-request Muse Spark explanation for a built-in synthetic finding."""
from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Callable
from urllib import error, request

from .audit import AuditTrace, Finding, model_evidence


ENDPOINT = 'https://inference.baseten.co/v1/chat/completions'
MODEL = 'meta-models/muse-spark-open-1026'
MAX_RESPONSE_BYTES = 1_000_000
SYSTEM_MESSAGE = (
    'Explain the supplied synthetic audit event in concise plain English. '
    'Reference the event ID, the supplied gate result, observed value and limit. '
    'If the session policy is unknown, say the limit is unknown. '
    'Use only the given evidence; do not invent facts or trade recommendations. '
    'A single gate PASS does not grant trade permission or overall eligibility. '
    'Never change the outcome. State that the data is synthetic.'
)


@dataclass(frozen=True)
class Explanation:
    status: str
    reason: str
    text: str = ''


class TransportError(Exception):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _post(url: str, key: str, payload: dict, timeout: float) -> dict:
    req = request.Request(
        url,
        data=json.dumps(payload, allow_nan=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key},
        method='POST',
    )
    try:
        with request.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise TransportError('RESPONSE_TOO_LARGE')
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TransportError('INVALID_RESPONSE')
        return value
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            code = 'ACCESS_DENIED'
        elif exc.code == 429:
            code = 'RATE_LIMITED'
        else:
            code = 'HTTP_ERROR'
        # HTTPError can own a response stream even though open() raised.
        # Close it without allowing a cleanup error to leak provider details.
        try:
            exc.close()
        except Exception:
            pass
        raise TransportError(code) from None
    except (socket.timeout, TimeoutError):
        raise TransportError('TIMEOUT') from None
    except error.URLError as exc:
        raise TransportError('TIMEOUT' if isinstance(exc.reason, (socket.timeout, TimeoutError)) else 'CONNECTION_ERROR') from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise TransportError('INVALID_RESPONSE') from None


Transport = Callable[[str, str, dict, float], dict]


def explain(trace: AuditTrace, finding: Finding, api_key: str, *, transport: Transport = _post) -> Explanation:
    try:
        evidence = model_evidence(trace, finding)
    except (ValueError, TypeError, AttributeError):
        return Explanation('UNAVAILABLE', 'INVALID_EVIDENCE')
    if not isinstance(api_key, str) or not api_key.strip() or api_key.strip() == 'your_baseten_api_key_here':
        return Explanation('UNAVAILABLE', 'KEY_MISSING')
    body = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_MESSAGE},
            {'role': 'user', 'content': json.dumps(evidence, sort_keys=True, allow_nan=False)},
        ],
        'max_tokens': 1024,
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
        text = choice['message']['content']
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            return Explanation('UNAVAILABLE', 'INVALID_RESPONSE')
        return Explanation('AVAILABLE', 'MODEL_EXPLANATION', text.strip())
    except TransportError as exc:
        allowed = {'RESPONSE_TOO_LARGE', 'ACCESS_DENIED', 'RATE_LIMITED', 'HTTP_ERROR', 'TIMEOUT', 'CONNECTION_ERROR', 'INVALID_RESPONSE'}
        return Explanation('UNAVAILABLE', str(exc) if str(exc) in allowed else 'MODEL_UNAVAILABLE')
    except (KeyError, IndexError, TypeError, AttributeError):
        return Explanation('UNAVAILABLE', 'INVALID_RESPONSE')
    except Exception:
        return Explanation('UNAVAILABLE', 'MODEL_UNAVAILABLE')
