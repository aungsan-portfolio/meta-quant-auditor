"""Read-only synthetic cancellation and portfolio-exposure audit.

This event-window implementation does not import or execute a trading engine.
Every input is a constrained fictional record; no broker connection exists.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json
from math import isfinite
import re
from uuid import NAMESPACE_URL, uuid5


SCHEMA = 'mqa.synthetic-lifecycle.v1'
MAX_BYTES = 65_536
MAX_EVENTS = 40
_EVENT_ID = re.compile(r'^E-[0-9]{1,4}$')
_UTC = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
_TERMINAL = frozenset({'CANCELED', 'EXPIRED', 'REJECTED', 'FILLED'})
_ORDER_STATUSES = frozenset({'NEW', 'ACCEPTED', 'PENDING_CANCEL', 'PARTIALLY_FILLED',
                             'CANCELED', 'EXPIRED', 'REJECTED', 'FILLED', 'UNKNOWN'})
_PROTECTION_STATUSES = frozenset({'ACTIVE', 'PENDING_CANCEL', 'MISSING', 'UNKNOWN'})


class LifecycleError(ValueError):
    """Invalid input; errors do not include uploaded values."""


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    observed_utc: str
    kind: str
    status: str | None = None
    cumulative_fill: float | None = None
    broker_event_utc: str | None = None
    position_qty: float | None = None
    coverage_qty: float | None = None


@dataclass(frozen=True, slots=True)
class ExposurePosition:
    market_value: float | None
    risk_to_stop: float | None


@dataclass(frozen=True, slots=True)
class ExposureInput:
    equity: float | None
    gross_cap_pct: float | None
    heat_cap_pct: float | None
    positions: tuple[ExposurePosition, ...]


@dataclass(frozen=True, slots=True)
class QuoteInput:
    bid: float | None
    ask: float | None
    age_seconds: float | None
    session: str
    regular_max_age: float | None
    extended_max_age: float | None
    max_spread_pct: float | None


@dataclass(frozen=True, slots=True)
class LifecycleTrace:
    events: tuple[Event, ...]
    quote: QuoteInput | None
    exposure: ExposureInput | None


@dataclass(frozen=True, slots=True)
class Finding:
    event_id: str
    code: str
    severity: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExposureResult:
    gross_pct: float | None
    gross_cap_pct: float | None
    gross_status: str
    heat_pct: float | None
    heat_cap_pct: float | None
    heat_status: str


@dataclass(frozen=True, slots=True)
class QuoteResult:
    age_seconds: float | None
    age_limit_seconds: float | None
    session: str
    freshness_status: str
    freshness_reason: str
    spread_pct: float | None
    spread_cap_pct: float | None
    spread_status: str
    spread_reason: str


@dataclass(frozen=True, slots=True)
class LifecycleReport:
    trace_id: str
    source_trace: LifecycleTrace
    events: tuple[Event, ...]
    findings: tuple[Finding, ...]
    current_gate: str
    current_reason: str
    quote: QuoteResult | None
    exposure: ExposureResult | None


def _object(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise LifecycleError('Unexpected or missing synthetic fields.')
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleError('Duplicate JSON property.')
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise LifecycleError('Non-finite JSON number.')


def _number(value: object, *, signed: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LifecycleError('A numeric field has an invalid type.')
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise LifecycleError('A numeric field is not finite.') from None
    if not isfinite(result) or abs(result) > 1_000_000_000 or (not signed and result < 0):
        raise LifecycleError('A numeric field is outside the demonstration range.')
    return result


def parse_trace(raw: bytes | str) -> LifecycleTrace:
    """Accept only a bounded, closed synthetic format and numeric identifiers."""
    if isinstance(raw, str):
        try:
            raw = raw.encode('utf-8')
        except UnicodeEncodeError:
            raise LifecycleError('Trace must be UTF-8 JSON.') from None
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise LifecycleError('Trace must be bounded UTF-8 JSON.')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except LifecycleError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise LifecycleError('Trace must be valid UTF-8 JSON.') from None
    root = _object(value, {'schema', 'synthetic', 'events', 'quote', 'exposure'})
    if root['schema'] != SCHEMA or root['synthetic'] is not True:
        raise LifecycleError('Only the documented synthetic lifecycle format is supported.')
    if not isinstance(root['events'], list) or not 1 <= len(root['events']) <= MAX_EVENTS:
        raise LifecycleError('Trace must contain between 1 and 40 events.')
    events, seen, previous = [], set(), None
    base = {'event_id', 'observed_utc', 'type'}
    fields = {'BROKER_ORDER': base | {'status', 'cumulative_fill'},
              'BROKER_FILL': base | {'status', 'cumulative_fill', 'broker_event_utc'},
              'CANCEL_REQUESTED': base, 'QUERY_FAILED': base,
              'RESERVATION_RELEASED': base, 'POSITION_OBSERVED': base | {'position_qty'},
              'PROTECTION_OBSERVED': base | {'status', 'coverage_qty'}}
    for raw_event in root['events']:
        if not isinstance(raw_event, dict) or not isinstance(raw_event.get('type'), str):
            raise LifecycleError('A lifecycle event has an invalid type.')
        kind = raw_event['type']
        if kind not in fields:
            raise LifecycleError('Unsupported lifecycle event.')
        item = _object(raw_event, fields[kind])
        event_id, observed = item['event_id'], item['observed_utc']
        if not isinstance(event_id, str) or not _EVENT_ID.fullmatch(event_id) or event_id in seen:
            raise LifecycleError('Synthetic event IDs must be unique numeric IDs.')
        if not isinstance(observed, str) or not _UTC.fullmatch(observed):
            raise LifecycleError('Observation time must be UTC with a Z suffix.')
        try:
            moment = datetime.strptime(observed, '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            raise LifecycleError('Observation time is invalid.') from None
        if previous is not None and moment <= previous:
            raise LifecycleError('Synthetic observations must have strictly increasing timestamps.')
        previous = moment
        seen.add(event_id)
        status = item.get('status')
        if kind in ('BROKER_ORDER', 'BROKER_FILL') and (not isinstance(status, str) or status not in _ORDER_STATUSES):
            raise LifecycleError('Unsupported synthetic order status.')
        if kind == 'BROKER_FILL' and status not in ('FILLED', 'PARTIALLY_FILLED'):
            raise LifecycleError('A synthetic fill must have a fill status.')
        if kind == 'PROTECTION_OBSERVED' and (not isinstance(status, str) or status not in _PROTECTION_STATUSES):
            raise LifecycleError('Unsupported synthetic protection status.')
        broker_time = item.get('broker_event_utc')
        if kind == 'BROKER_FILL':
            if not isinstance(broker_time, str) or not _UTC.fullmatch(broker_time):
                raise LifecycleError('Synthetic broker event time must be UTC with a Z suffix.')
            try:
                actual = datetime.strptime(broker_time, '%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                raise LifecycleError('Synthetic broker event time is invalid.') from None
            if actual > moment:
                raise LifecycleError('Synthetic broker event time cannot follow observation time.')
        events.append(Event(event_id, observed, kind, status,
                            _number(item.get('cumulative_fill')),
                            broker_time,
                            _number(item.get('position_qty')),
                            _number(item.get('coverage_qty'))))

    quote = None
    if root['quote'] is not None:
        q = _object(root['quote'], {'bid', 'ask', 'age_seconds', 'session',
                                    'regular_max_age', 'extended_max_age', 'max_spread_pct'})
        session = q['session']
        if not isinstance(session, str) or session not in {'REGULAR', 'EXTENDED', 'UNKNOWN'}:
            raise LifecycleError('Unsupported synthetic quote session.')
        quote = QuoteInput(_number(q['bid']), _number(q['ask']), _number(q['age_seconds']), session,
                           _number(q['regular_max_age']), _number(q['extended_max_age']), _number(q['max_spread_pct']))

    exposure = None
    if root['exposure'] is not None:
        obj = _object(root['exposure'], {'equity', 'gross_cap_pct', 'heat_cap_pct', 'positions'})
        if not isinstance(obj['positions'], list) or len(obj['positions']) > 32:
            raise LifecycleError('Synthetic exposure accepts at most 32 positions.')
        positions = []
        for item in obj['positions']:
            position = _object(item, {'market_value', 'risk_to_stop'})
            positions.append(ExposurePosition(_number(position['market_value'], signed=True),
                                              _number(position['risk_to_stop'])))
        equity = _number(obj['equity'])
        if equity is not None and 0 < equity < 0.01:
            raise LifecycleError('Synthetic equity is below the supported demonstration range.')
        exposure = ExposureInput(equity, _number(obj['gross_cap_pct']),
                                 _number(obj['heat_cap_pct']), tuple(positions))
    return LifecycleTrace(tuple(events), quote, exposure)


def _input_object(trace: LifecycleTrace) -> dict:
    events = []
    for event in trace.events:
        item = {'event_id': event.event_id, 'observed_utc': event.observed_utc, 'type': event.kind}
        if event.kind in ('BROKER_ORDER', 'BROKER_FILL'):
            item.update(status=event.status, cumulative_fill=event.cumulative_fill)
            if event.kind == 'BROKER_FILL':
                item['broker_event_utc'] = event.broker_event_utc
        elif event.kind == 'POSITION_OBSERVED':
            item['position_qty'] = event.position_qty
        elif event.kind == 'PROTECTION_OBSERVED':
            item.update(status=event.status, coverage_qty=event.coverage_qty)
        events.append(item)
    return {'schema': SCHEMA, 'synthetic': True, 'events': events,
            'quote': asdict(trace.quote) if trace.quote is not None else None,
            'exposure': asdict(trace.exposure) if trace.exposure is not None else None}


def _quote(value: QuoteInput | None) -> QuoteResult | None:
    if value is None:
        return None
    age_limit = {'REGULAR': value.regular_max_age, 'EXTENDED': value.extended_max_age}.get(value.session)
    if value.session == 'UNKNOWN':
        freshness_status, freshness_reason = 'BLOCK', 'SESSION_POLICY_UNKNOWN'
    elif value.age_seconds is None or age_limit is None:
        freshness_status, freshness_reason = 'UNKNOWN', 'FRESHNESS_EVIDENCE_MISSING'
    elif value.age_seconds > age_limit:
        freshness_status, freshness_reason = 'BLOCK', 'QUOTE_STALE'
    else:
        freshness_status, freshness_reason = 'PASS', 'WITHIN_AGE_LIMIT'
    spread = None
    if value.bid is None or value.ask is None:
        spread_status, spread_reason = 'UNKNOWN', 'QUOTE_PRICES_MISSING'
    elif value.bid <= 0 or value.ask <= 0 or value.ask < value.bid:
        spread_status, spread_reason = 'BLOCK', 'QUOTE_INVALID_OR_CROSSED'
    else:
        bid, ask = Decimal(str(value.bid)), Decimal(str(value.ask))
        spread = float(((ask - bid) / ((ask + bid) / 2) * 100)
                       .quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP))
        if value.max_spread_pct is None:
            spread_status, spread_reason = 'UNKNOWN', 'SPREAD_LIMIT_MISSING'
        elif spread > value.max_spread_pct:
            spread_status, spread_reason = 'VETO', 'SPREAD_TOO_WIDE'
        else:
            spread_status, spread_reason = 'PASS', 'WITHIN_SPREAD_LIMIT'
    return QuoteResult(value.age_seconds, age_limit, value.session, freshness_status, freshness_reason,
                       spread, value.max_spread_pct, spread_status, spread_reason)


def _exposure(value: ExposureInput | None) -> ExposureResult | None:
    if value is None:
        return None
    # Each output is computed independently: a missing stop risk must not hide
    # a gross-exposure breach, and a missing market value must not hide heat.
    equity = value.equity
    gross = heat = None
    if equity is not None and equity > 0:
        denom = Decimal(str(equity))
        quantum = Decimal('0.000001')
        if all(p.market_value is not None for p in value.positions):
            gross = float((sum(abs(Decimal(str(p.market_value))) for p in value.positions) / denom * 100)
                          .quantize(quantum, rounding=ROUND_HALF_UP))
        if all(p.risk_to_stop is not None for p in value.positions):
            heat = float((sum(Decimal(str(p.risk_to_stop)) for p in value.positions) / denom * 100)
                         .quantize(quantum, rounding=ROUND_HALF_UP))
    gross_status = 'UNKNOWN' if gross is None or value.gross_cap_pct is None else 'VETO' if gross > value.gross_cap_pct else 'PASS'
    heat_status = 'UNKNOWN' if heat is None or value.heat_cap_pct is None else 'VETO' if heat > value.heat_cap_pct else 'PASS'
    return ExposureResult(gross, value.gross_cap_pct, gross_status, heat, value.heat_cap_pct, heat_status)


def audit_trace(trace: LifecycleTrace) -> LifecycleReport:
    """Review supplied observations; never perform or authorize trading actions."""
    if not isinstance(trace, LifecycleTrace):
        raise LifecycleError('A validated synthetic trace is required.')
    # Revalidate even programmatically constructed dataclasses before computing
    # facts or passing any content to a model.
    try:
        canonical = json.dumps(_input_object(trace), sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, AttributeError):
        raise LifecycleError('Invalid synthetic trace object.') from None
    trace = parse_trace(canonical)
    trace_id = str(uuid5(NAMESPACE_URL, 'mqa-lifecycle-v1:' + canonical))
    status, fill, max_fill = 'UNKNOWN', None, None
    position, protection, coverage = None, 'UNKNOWN', None
    status_ref = position_ref = protection_ref = cancel_ref = release_ref = None
    release_time = None
    conflict = False
    terminal_seen = None
    findings = []

    def gate() -> tuple[str, str]:
        if conflict:
            return 'BLOCK', 'CONTRADICTORY_BROKER_EVIDENCE'
        if status == 'UNKNOWN' or fill is None:
            return 'BLOCK', 'BROKER_TRUTH_UNKNOWN'
        if status not in _TERMINAL:
            return 'BLOCK', 'ORDER_NOT_TERMINAL'
        if fill == 0:
            return 'PASS', 'TERMINAL_ZERO_FILL_CONFIRMED'
        if position is None:
            return 'BLOCK', 'POSITION_RECONCILIATION_REQUIRED'
        if position == 0:
            return 'PASS', 'TERMINAL_POSITION_FLAT'
        if protection != 'ACTIVE' or coverage is None:
            return 'BLOCK', 'PROTECTION_NOT_CONFIRMED'
        if Decimal(str(coverage)) != Decimal(str(position)):
            return 'BLOCK', 'PROTECTION_QUANTITY_MISMATCH'
        return 'PASS', 'SYNTHETIC_TERMINAL_COVERAGE_MATCH'

    for event in trace.events:
        if event.kind == 'CANCEL_REQUESTED':
            cancel_ref = event.event_id
        elif event.kind == 'QUERY_FAILED':
            status, fill, status_ref = 'UNKNOWN', None, event.event_id
            position, protection, coverage = None, 'UNKNOWN', None
            position_ref = protection_ref = None
        elif event.kind in ('BROKER_ORDER', 'BROKER_FILL'):
            old_max = max_fill
            status, fill, status_ref = event.status, event.cumulative_fill, event.event_id
            if status == 'UNKNOWN' or fill is None:
                status, fill = 'UNKNOWN', None
                position, protection, coverage = None, 'UNKNOWN', None
                position_ref = protection_ref = None
            else:
                if (terminal_seen is not None and status != terminal_seen) or (old_max is not None and fill < old_max):
                    conflict = True
                    findings.append(Finding(event.event_id, 'CONTRADICTORY_BROKER_EVIDENCE', 'WARNING', (event.event_id,)))
                if status in _TERMINAL:
                    terminal_seen = status
                if status in ('FILLED', 'PARTIALLY_FILLED') and fill == 0:
                    conflict = True
                    findings.append(Finding(event.event_id, 'FILL_STATUS_WITH_ZERO_QUANTITY', 'WARNING', (event.event_id,)))
                increased = ((old_max is None and fill > 0) or (old_max is not None and fill > old_max))
                max_fill = max(fill, old_max) if old_max is not None else fill
                # After every positive-fill broker observation, require fresh
                # position and protection observations before a release can pass.
                if fill > 0:
                    position, protection, coverage = None, 'UNKNOWN', None
                    position_ref = protection_ref = None
                if increased:
                    if cancel_ref:
                        findings.append(Finding(event.event_id, 'FILL_OBSERVED_AFTER_CANCEL_REQUEST', 'INFO', (cancel_ref, event.event_id)))
                    if release_ref:
                        # A later observation alone does not prove a later fill.
                        # Distinguish supplied broker event time from local observation.
                        reported_later = (event.broker_event_utc is not None and
                                          release_time is not None and
                                          event.broker_event_utc > release_time and old_max is not None)
                        code = 'LATE_FILL_AFTER_RELEASE' if reported_later else 'FILL_OBSERVED_AFTER_RELEASE'
                        findings.append(Finding(event.event_id, code, 'CRITICAL' if reported_later else 'WARNING', (release_ref, event.event_id)))
        elif event.kind == 'POSITION_OBSERVED':
            position, position_ref = event.position_qty, event.event_id
            protection, coverage, protection_ref = 'UNKNOWN', None, None
        elif event.kind == 'PROTECTION_OBSERVED':
            protection, coverage, protection_ref = event.status, event.coverage_qty, event.event_id
        elif event.kind == 'RESERVATION_RELEASED':
            result, reason = gate()
            refs = tuple(ref for ref in (status_ref, position_ref, protection_ref, event.event_id) if ref)
            if release_ref:
                findings.append(Finding(event.event_id, 'DUPLICATE_RESERVATION_RELEASE', 'WARNING', (release_ref, event.event_id)))
            findings.append(Finding(event.event_id, 'RELEASE_' + reason, 'PASS' if result == 'PASS' else 'CRITICAL', refs))
            release_ref = event.event_id
            release_time = event.observed_utc
    current_gate, current_reason = gate()
    return LifecycleReport(trace_id, trace, trace.events, tuple(findings), current_gate, current_reason,
                           _quote(trace.quote), _exposure(trace.exposure))


def model_evidence(report: LifecycleReport) -> dict:
    """Return only the strictly constructed fictional events and conclusions."""
    if not isinstance(report, LifecycleReport) or audit_trace(report.source_trace) != report:
        raise LifecycleError('Unverified synthetic report.')
    return {'schema': 'mqa.synthetic-lifecycle-report.v1', 'synthetic': True,
            'trace_id': report.trace_id, 'scope': 'One simulated order; no broker, order or trade authorization.',
            'events': [asdict(e) for e in report.events],
            'findings': [{'event_id': f.event_id, 'code': f.code, 'severity': f.severity,
                          'evidence_refs': list(f.evidence_refs)} for f in report.findings],
            'current_gate': report.current_gate, 'current_reason': report.current_reason,
            'quote': asdict(report.quote) if report.quote else None,
            'exposure': asdict(report.exposure) if report.exposure else None}


def markdown_report(report: LifecycleReport, explanation: str | None = None) -> str:
    def show(value, unit: str) -> str:
        return 'unknown' if value is None else f'{value}{unit}'

    lines = ['# Synthetic Cancellation Safety Audit', '', f'Trace: `{report.trace_id}`',
             '', '**Simulation only. No broker action or trade authorization.**', '',
             f'Current G03 gate: **{report.current_gate}** — `{report.current_reason}`', '']
    if report.quote:
        q = report.quote
        lines.extend(['## G01 and G02: Synthetic quote checks', '',
                      f'- Freshness: {show(q.age_seconds, " seconds")} / limit {show(q.age_limit_seconds, " seconds")} — **{q.freshness_status}** (`{q.freshness_reason}`)',
                      f'- Spread: {show(q.spread_pct, "%")} / cap {show(q.spread_cap_pct, "%")} — **{q.spread_status}** (`{q.spread_reason}`)', ''])
    else:
        lines.extend(['## G01 and G02: Synthetic quote checks', '',
                      'Quote input was not provided; no PASS is inferred.', ''])
    lines.extend([
             '| Observed UTC | Broker event UTC | Event ID | Event | Status | Fill | Position | Coverage |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |'])
    for e in report.events:
        lines.append(f'| {e.observed_utc} | {e.broker_event_utc if e.broker_event_utc is not None else "—"} | {e.event_id} | {e.kind} | {e.status if e.status is not None else "—"} | {e.cumulative_fill if e.cumulative_fill is not None else "—"} | {e.position_qty if e.position_qty is not None else "—"} | {e.coverage_qty if e.coverage_qty is not None else "—"} |')
    lines.extend(['', '## Recorded findings', '', '| Event | Severity | Finding | Evidence |', '| --- | --- | --- | --- |'])
    for finding in report.findings:
        lines.append(f'| {finding.event_id} | {finding.severity} | {finding.code} | {", ".join(finding.evidence_refs)} |')
    if not report.findings:
        lines.append('| — | — | No release or anomaly recorded | — |')
    if report.exposure:
        e = report.exposure
        lines.extend(['', '## G04: Synthetic portfolio measures', '',
                      f'- Gross exposure: {show(e.gross_pct, "%")} / cap {show(e.gross_cap_pct, "%")} — **{e.gross_status}**',
                      f'- Stop-risk heat: {show(e.heat_pct, "%")} / cap {show(e.heat_cap_pct, "%")} — **{e.heat_status}**',
                      '- Stop-risk inputs are supplied by the example, not verified actual losses.'])
    else:
        lines.extend(['', '## G04: Synthetic portfolio measures', '',
                      'Exposure input was not provided; no PASS is inferred.'])
    if explanation:
        lines.extend(['', '## Unverified model explanation', '',
                      'Compare every claim with the deterministic evidence above.', '', explanation.strip()])
    return '\n'.join(lines) + '\n'


def sample_traces() -> dict[str, dict]:
    """New fictional scenarios, inspired by domain concepts, not copied records."""
    def ev(number, kind, **data):
        return {'event_id': f'E-{number:03}', 'observed_utc': f'2026-10-27T14:30:{number:02}Z', 'type': kind, **data}
    quote = {'bid': 99.95, 'ask': 100.05, 'age_seconds': 1.2, 'session': 'REGULAR',
             'regular_max_age': 5.0, 'extended_max_age': 90.0, 'max_spread_pct': 0.4}
    def trace(events, exposure=None):
        return {'schema': SCHEMA, 'synthetic': True, 'events': events,
                'quote': dict(quote), 'exposure': exposure}
    baseline = {'equity': 100_000, 'gross_cap_pct': 100, 'heat_cap_pct': 2,
                'positions': [{'market_value': 35_000, 'risk_to_stop': 600},
                              {'market_value': -20_000, 'risk_to_stop': 300}]}
    high = {'equity': 100_000, 'gross_cap_pct': 100, 'heat_cap_pct': 2,
            'positions': [{'market_value': 90_000, 'risk_to_stop': 1_600},
                          {'market_value': -30_000, 'risk_to_stop': 700}]}
    return {
        'Pending cancel → early release → late fill': trace([
            ev(1, 'BROKER_ORDER', status='NEW', cumulative_fill=0), ev(2, 'CANCEL_REQUESTED'),
            ev(3, 'BROKER_ORDER', status='PENDING_CANCEL', cumulative_fill=0),
            ev(4, 'RESERVATION_RELEASED'), ev(5, 'BROKER_FILL', status='FILLED', cumulative_fill=4,
                                             broker_event_utc='2026-10-27T14:30:05Z'),
        ], baseline),
        'Cancel confirmed with zero fill': trace([
            ev(1, 'BROKER_ORDER', status='NEW', cumulative_fill=0), ev(2, 'CANCEL_REQUESTED'),
            ev(3, 'BROKER_ORDER', status='CANCELED', cumulative_fill=0), ev(4, 'RESERVATION_RELEASED'),
        ], baseline),
        'Broker query unavailable': trace([
            ev(1, 'BROKER_ORDER', status='NEW', cumulative_fill=0), ev(2, 'CANCEL_REQUESTED'),
            ev(3, 'QUERY_FAILED'), ev(4, 'RESERVATION_RELEASED'),
        ], None),
        'Partial fill with confirmed protection': trace([
            ev(1, 'BROKER_ORDER', status='NEW', cumulative_fill=0), ev(2, 'CANCEL_REQUESTED'),
            ev(3, 'BROKER_ORDER', status='PARTIALLY_FILLED', cumulative_fill=2),
            ev(4, 'BROKER_ORDER', status='CANCELED', cumulative_fill=2),
            ev(5, 'POSITION_OBSERVED', position_qty=2),
            ev(6, 'PROTECTION_OBSERVED', status='ACTIVE', coverage_qty=2),
            ev(7, 'RESERVATION_RELEASED'),
        ], baseline),
        'Exposure and heat exceed caps': trace([
            ev(1, 'BROKER_ORDER', status='CANCELED', cumulative_fill=0), ev(2, 'RESERVATION_RELEASED'),
        ], high),
    }
