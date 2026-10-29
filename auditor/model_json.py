"""Normalize one complete JSON envelope without extracting embedded content."""
from __future__ import annotations

import re


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
