"""Normalize one complete JSON envelope without extracting embedded content."""
from __future__ import annotations

import re
import json
from math import isfinite


_FENCE = re.compile(r'```(?:json)?[ \t]*\r?\n(.*)\r?\n```', re.IGNORECASE | re.DOTALL)


def unwrap_json_response(text: str) -> str:
    """Accept bare JSON or one whole-response JSON/unlabelled Markdown fence.

    Callers bound the original response length and retain their own strict JSON
    hooks and schema checks. Prose is never searched for a plausible JSON object.
    """
    stripped = text.strip()
    if not stripped.startswith('```'):
        return stripped
    match = _FENCE.fullmatch(stripped)
    if match is None:
        raise ValueError('Unsupported JSON response envelope.')
    return match.group(1)


def strict_json_object(text: str, *, max_chars: int = 12_000) -> dict:
    """Decode a bounded object, rejecting duplicate keys and nonfinite numbers.

    Reuses the whole-response envelope accepted by the existing claim parsers.
    Schema validation remains the caller's responsibility. Overflowing exponents
    (e.g. 1e999) are rejected as well as JSON's nonstandard NaN/Infinity tokens.
    """
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON property.')
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError('Nonfinite JSON number.')

    def number(value):
        parsed = float(value)
        if not isfinite(parsed):
            raise ValueError('Nonfinite JSON number.')
        return parsed

    if type(text) is not str or not text.strip() or len(text) > max_chars:
        raise ValueError('Empty or oversized JSON response.')
    result = json.loads(unwrap_json_response(text), object_pairs_hook=pairs,
                        parse_constant=reject_constant, parse_float=number)
    if type(result) is not dict:
        raise ValueError('JSON object required.')
    return result
