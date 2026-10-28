"""Explicit, data-minimized Muse explanations of one reported gate record.

No account, symbol, strategy, exact time, price, order ID or original source
record is sent. A match only compares model claims with reported local fields;
it does not verify broker truth, event provenance or the model's interpretation.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, NamedTuple

from .model import Explanation, _post
from .paper_observer import DECISIONS, REASONS, STAGES, _event_is_valid
from .workbench_model import _explain


PAPER_SOURCE = 'DECLARED_PREEXISTING_PAPER_BOT'
SYNTHETIC_SOURCE = 'SYNTHETIC_REPLAY'
FIELDS = ('stage', 'decision', 'reason')
UNKNOWN = frozenset({'OTHER_OR_UNKNOWN', 'NOT_RECORDED'})
MAX_TEXT_CHARS = 12_000

SYSTEM = (
    'You are explaining a single reported gate-record label to a human reviewer. '
    'The input may be a fictional replay or a user-declared pre-existing paper-bot record; '
    'the source and paper mode are not independently verified. Return only a JSON object '
    'with exactly claims and interpretation. claims must contain exactly three objects: '
    '{"field":"stage","value":"..."}, {"field":"decision","value":"..."}, '
    '{"field":"reason","value":"..."}. Copy the values exactly from the input. '
    'interpretation must be short plain English based only on those labels. '
    'Treat OTHER_OR_UNKNOWN and NOT_RECORDED as unknown; do not invent their meaning. '
    'No score, threshold, quote, price, position, stop, fill, account, broker confirmation, '
    'loss avoided or overall eligibility is provided. State that relevant evidence is missing. '
    'Do not make trading recommendations, assert that risk was prevented, or authorize a trade. '
    'A single PASS or REJECT is a reported gate record, not a complete trade decision. '
    'No markdown fences or additional keys.'
)


class PaperEvidenceError(ValueError):
    """Invalid local evidence or response; never includes source or model text."""


@dataclass(frozen=True, slots=True)
class PaperEvidence:
    trace_id: str
    source_kind: str
    stage: str
    decision: str
    reason: str

    @property
    def job_identity(self) -> str:
        # Bind a result to both the local record identity and the sent labels.
        raw = json.dumps({'trace_id': self.trace_id, 'facts': self.sent_facts()},
                         sort_keys=True, separators=(',', ':'), allow_nan=False)
        return sha256(raw.encode('utf-8')).hexdigest()

    def sent_facts(self) -> dict[str, str]:
        return {'source_kind': self.source_kind, 'stage': self.stage,
                'decision': self.decision, 'reason': self.reason}


class PaperSelection(NamedTuple):
    event_id: str = 'PAPER_REPORTED_GATE'


@dataclass(frozen=True, slots=True)
class CheckedPaperClaim:
    field: str
    claimed: str
    reported: str
    status: str


@dataclass(frozen=True, slots=True)
class CheckedPaperResponse:
    claims: tuple[CheckedPaperClaim, ...]
    interpretation: str

    @property
    def has_contradiction(self) -> bool:
        return any(claim.status == 'CONTRADICTION' for claim in self.claims)


def _valid_evidence(evidence: Any) -> bool:
    if not isinstance(evidence, PaperEvidence):
        return False
    return (evidence.source_kind in (PAPER_SOURCE, SYNTHETIC_SOURCE)
            and isinstance(evidence.trace_id, str) and len(evidence.trace_id) == 64
            and all(c in '0123456789abcdef' for c in evidence.trace_id)
            and isinstance(evidence.stage, str) and evidence.stage in set(STAGES.values()) | {'OTHER_OR_UNKNOWN'}
            and isinstance(evidence.decision, str) and evidence.decision in DECISIONS | {'OTHER_OR_UNKNOWN'}
            and isinstance(evidence.reason, str) and evidence.reason in REASONS | UNKNOWN)


def build_evidence(event: Any, source_kind: str) -> PaperEvidence:
    """Validate the closed event schema and bind jobs to the full local record."""
    if source_kind not in (PAPER_SOURCE, SYNTHETIC_SOURCE):
        raise PaperEvidenceError('Invalid source kind')
    try:
        valid = _event_is_valid(event)
    except (TypeError, ValueError, KeyError):
        valid = False
    if not valid:
        raise PaperEvidenceError('Invalid normalized gate record')
    # Local identity covers the full normalized event and source. It is not
    # included in the provider payload and is not a signed provenance record.
    encoded = json.dumps({'source': source_kind, 'event': event}, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    identity = sha256(encoded).hexdigest()
    return PaperEvidence(identity, source_kind, event['stage'], event['decision'], event['reason'])


def explain_paper_event(evidence: PaperEvidence, _selection: PaperSelection, api_key: str,
                        *, transport=_post) -> Explanation:
    if not _valid_evidence(evidence):
        return Explanation('UNAVAILABLE', 'INVALID_EVIDENCE')
    return _explain(SYSTEM, evidence.sent_facts(), api_key, transport)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PaperEvidenceError('Duplicate response field')
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise PaperEvidenceError('Invalid response number')


def verify_paper_response(evidence: PaperEvidence, response_text: str) -> CheckedPaperResponse:
    """Check three exact label claims. Narrative meaning remains unverified."""
    if not _valid_evidence(evidence):
        raise PaperEvidenceError('Invalid evidence')
    if not isinstance(response_text, str) or not response_text.strip() or len(response_text) > MAX_TEXT_CHARS:
        raise PaperEvidenceError('Empty or oversized response')
    try:
        obj = json.loads(response_text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, TypeError, RecursionError):
        raise PaperEvidenceError('Response is not valid structured JSON') from None
    if not isinstance(obj, dict) or set(obj) != {'claims', 'interpretation'}:
        raise PaperEvidenceError('Response has an invalid shape')
    claims, interpretation = obj['claims'], obj['interpretation']
    if (not isinstance(claims, list) or len(claims) != len(FIELDS)
            or type(interpretation) is not str or not interpretation.strip()
            or len(interpretation) > 4000):
        raise PaperEvidenceError('Response has invalid claims or interpretation')
    expected = evidence.sent_facts()
    seen: set[str] = set()
    checked = []
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {'field', 'value'}:
            raise PaperEvidenceError('A claim has an invalid shape')
        field, value = claim['field'], claim['value']
        if type(field) is not str or field not in FIELDS or field in seen:
            raise PaperEvidenceError('Claim field is invalid or repeated')
        if type(value) is not str or len(value) > 128:
            raise PaperEvidenceError('Claim value has an invalid type')
        seen.add(field)
        reported = expected[field]
        if reported in UNKNOWN:
            status = 'UNVERIFIED'
        elif value == reported:
            status = 'EVIDENCE_MATCH'
        else:
            status = 'CONTRADICTION'
        checked.append(CheckedPaperClaim(field, value, reported, status))
    if seen != set(FIELDS):
        raise PaperEvidenceError('Required claim fields are missing')
    return CheckedPaperResponse(tuple(checked), interpretation.strip())
