"""A bounded, read-only view of selected, operator-supplied gate observations.

This module does not access a broker, verify that a source is a paper account,
or send any source records to a model. The exported event format is new to this
project; it is intentionally much smaller than the source ledger.
"""
from __future__ import annotations

import json
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc
EVENT_START = datetime(2026, 10, 26, 16, 0, tzinfo=UTC)  # Oct 26, noon ET
EVENT_END = datetime(2026, 11, 5, 2, 0, tzinfo=UTC)  # Nov 4, 9 pm ET
MAX_SOURCE_BYTES = 2_000_000
MAX_SNAPSHOT_BYTES = 100_000
MAX_EVENTS = 200
SNAPSHOT_FORMAT = 'mqa.paper-gate-observations.v1'
SOURCE_NAME = 'DECLARED_PREEXISTING_PAPER_BOT'
SYMBOL_PATTERN = re.compile(r'^[A-Z]{1,5}$')

# Unrecognized source labels are discarded rather than displayed verbatim.
STRATEGIES = frozenset({'GAP_AND_GO', 'CANDLESTICK', 'ORB', 'VWAP_BOUNCE',
                        'MOMENTUM_SCALP', 'MEAN_REVERSION'})
STAGES = {
    'STAGE_COVERAGE': 'DATA_COVERAGE',
    'STAGE_REGIME': 'MARKET_REGIME',
    'STAGE_LUNCH_CHOP': 'LUNCH_CHOP',
    'STAGE_PENDING_ORDER': 'PENDING_ORDER',
    'STAGE_QUOTE_HEALTH': 'QUOTE_HEALTH',
    'STAGE_MAX_CHASE': 'CHASE',
    'STAGE_SOXX_GUARD': 'SECTOR_GUARD',
    'STAGE_POSITION_SIZE': 'POSITION_SIZE',
    'STAGE_ORDER_EXECUTION': 'EXECUTION',
    'STAGE_ORDER_SUBMIT': 'SUBMISSION_REPORTED',
    'STAGE_FILLED': 'FILL_REPORTED',
}
DECISIONS = frozenset({'PASS', 'REJECT', 'BLOCK', 'VETO', 'ALLOW', 'SKIP'})
REASONS = frozenset({'STALE_QUOTE', 'EXCESSIVE_SPREAD', 'MAX_CHASE',
                     'DUPLICATE_ORDER', 'LUNCH_CHOP_ZONE', 'LOW_COVERAGE',
                     'NOISE_FLOOR', 'SOXX_TECH_LONG_VETO', 'STRATEGY_DISABLED',
                     'CONFIDENCE_BELOW_FLOOR', 'ENTRY_CUTOFF_TIME', 'SPY_BEARISH_5M',
                     'COUNTER_TREND_SHORT_VETO', 'PRIOR_EXIT_PENDING_RECONCILIATION',
                     'RSI_OVERBOUGHT', 'RSI_OVERSOLD', 'TECH_CLUSTER_CAP'})

# These are descriptions of source labels, not independent checks of their inputs.
REASON_DESCRIPTIONS = {
    'CONFIDENCE_BELOW_FLOOR': 'Reported score below its configured floor.',
    'ENTRY_CUTOFF_TIME': 'Reported entry-time cutoff.',
    'SPY_BEARISH_5M': 'Reported SPY benchmark guard.',
    'COUNTER_TREND_SHORT_VETO': 'Reported counter-trend short guard.',
    'PRIOR_EXIT_PENDING_RECONCILIATION': 'Reported earlier exit awaiting reconciliation.',
    'RSI_OVERBOUGHT': 'Reported RSI overbought condition.',
    'RSI_OVERSOLD': 'Reported RSI oversold condition.',
    'TECH_CLUSTER_CAP': 'Reported technology cluster concentration cap.',
    'EXCESSIVE_SPREAD': 'Reported quote spread above a limit.',
    'STALE_QUOTE': 'Reported quote too old.',
    'MAX_CHASE': 'Reported price exceeded the chase limit.',
    'DUPLICATE_ORDER': 'Reported duplicate order or candidate.',
    'LUNCH_CHOP_ZONE': 'Reported lunch-chop entry guard.',
    'LOW_COVERAGE': 'Reported insufficient data coverage.',
    'NOISE_FLOOR': 'Reported noise-floor guard.',
    'SOXX_TECH_LONG_VETO': 'Reported SOXX technology-long guard.',
    'STRATEGY_DISABLED': 'Reported strategy disabled.',
    'NOT_RECORDED': 'No source reason was recorded.',
    'OTHER_OR_UNKNOWN': 'Unknown label withheld; the source value was not displayed.',
}
EVENT_FIELDS = frozenset({'observed_utc', 'symbol', 'strategy', 'stage', 'decision', 'reason'})
SNAPSHOT_FIELDS = frozenset({'format', 'source', 'checked_utc', 'readable',
                             'source_tail_only', 'events_truncated', 'ignored_records', 'events'})


class ObservationError(ValueError):
    """A local observation or normalized snapshot is invalid."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ObservationError('Duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ObservationError('Invalid JSON constant')


def _json(value: str) -> Any:
    try:
        return json.loads(value, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ObservationError('Invalid JSON') from exc


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ObservationError('Invalid timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ObservationError('Timestamp needs a timezone')
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise ObservationError('Invalid timestamp') from exc


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ObservationError('Timestamp needs a timezone')
    return value.astimezone(UTC).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def normalize_record(record: Any) -> dict[str, str] | None:
    """Keep only bounded fields. A timestamp is not proof of provenance."""
    if not isinstance(record, dict):
        return None
    try:
        observed = _timestamp(record.get('timestamp'))
    except ObservationError:
        return None
    if not EVENT_START <= observed <= EVENT_END:
        return None
    symbol = record.get('symbol')
    if not isinstance(symbol, str) or not SYMBOL_PATTERN.fullmatch(symbol):
        return None

    def option(name: str, allowed: frozenset[str]) -> str:
        raw = record.get(name)
        return raw if isinstance(raw, str) and raw in allowed else 'OTHER_OR_UNKNOWN'

    raw_stage = record.get('stage')
    stage = STAGES.get(raw_stage, 'OTHER_OR_UNKNOWN') if isinstance(raw_stage, str) else 'OTHER_OR_UNKNOWN'
    raw_reason = record.get('reason_code')
    if raw_reason in (None, ''):
        reason = 'NOT_RECORDED'
    else:
        reason = raw_reason if isinstance(raw_reason, str) and raw_reason in REASONS else 'OTHER_OR_UNKNOWN'
    return {'observed_utc': _iso(observed), 'symbol': symbol,
            'strategy': option('strategy', STRATEGIES), 'stage': stage,
            'decision': option('decision', DECISIONS), 'reason': reason}


def _event_is_valid(event: Any) -> bool:
    if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
        return False
    try:
        stamp = _timestamp(event['observed_utc'])
    except ObservationError:
        return False
    return (EVENT_START <= stamp <= EVENT_END
            and isinstance(event['symbol'], str) and bool(SYMBOL_PATTERN.fullmatch(event['symbol']))
            and event['strategy'] in STRATEGIES | {'OTHER_OR_UNKNOWN'}
            and event['stage'] in set(STAGES.values()) | {'OTHER_OR_UNKNOWN'}
            and event['decision'] in DECISIONS | {'OTHER_OR_UNKNOWN'}
            and event['reason'] in REASONS | {'OTHER_OR_UNKNOWN', 'NOT_RECORDED'})


def capture_source(path: Path, *, checked: datetime) -> dict[str, Any]:
    """Read a bounded tail, discard raw records, and return a small snapshot."""
    base: dict[str, Any] = {'format': SNAPSHOT_FORMAT, 'source': SOURCE_NAME,
                            'checked_utc': _iso(checked), 'readable': False,
                            'source_tail_only': False, 'events_truncated': False,
                            'ignored_records': 0, 'events': []}
    try:
        if path.suffix.lower() != '.jsonl' or not stat.S_ISREG(path.stat().st_mode):
            return base
        with path.open('rb') as source:
            source.seek(0, 2)
            size = source.tell()
            source.seek(max(0, size - MAX_SOURCE_BYTES))
            data = source.read(MAX_SOURCE_BYTES)
        tail_only = size > MAX_SOURCE_BYTES
        if tail_only:
            data = data.partition(b'\n')[2]
        # Source writer may be halfway through its last line.
        lines = data.splitlines() if data.endswith(b'\n') else data.splitlines()[:-1]
        events: list[dict[str, str]] = []
        ignored = 0
        for line in lines:
            try:
                raw = _json(line.decode('utf-8'))
                event = normalize_record(raw)
            except (ObservationError, UnicodeDecodeError):
                event = None
            if event is None:
                ignored += 1
            else:
                events.append(event)
        base.update(readable=True, source_tail_only=tail_only, events_truncated=len(events) > MAX_EVENTS,
                    ignored_records=ignored, events=events[-MAX_EVENTS:])
    except (OSError, ValueError):
        # No source path, contents, or exception text is copied to the snapshot.
        pass
    return base


def read_snapshot(path: Path) -> dict[str, Any]:
    try:
        with path.open('rb') as source:
            data = source.read(MAX_SNAPSHOT_BYTES + 1)
        if len(data) > MAX_SNAPSHOT_BYTES:
            raise ObservationError('Snapshot is too large')
        doc = _json(data.decode('utf-8'))
        if not isinstance(doc, dict) or set(doc) != SNAPSHOT_FIELDS:
            raise ObservationError('Invalid snapshot fields')
        if doc['format'] != SNAPSHOT_FORMAT or doc['source'] != SOURCE_NAME:
            raise ObservationError('Invalid snapshot format')
        _timestamp(doc['checked_utc'])
        if any(type(doc[x]) is not bool for x in ('readable', 'source_tail_only', 'events_truncated')):
            raise ObservationError('Invalid snapshot status')
        if type(doc['ignored_records']) is not int or doc['ignored_records'] < 0:
            raise ObservationError('Invalid ignored count')
        if not isinstance(doc['events'], list) or len(doc['events']) > MAX_EVENTS:
            raise ObservationError('Invalid event list')
        if not all(_event_is_valid(e) for e in doc['events']):
            raise ObservationError('Invalid event')
        if not doc['readable'] and doc['events']:
            raise ObservationError('Unreadable source cannot contain events')
        return doc
    except (OSError, UnicodeDecodeError, TypeError) as exc:
        raise ObservationError('Snapshot unavailable or invalid') from exc


def poll_status(snapshot: dict[str, Any], *, now: datetime) -> str:
    """Report observer freshness, not broker health or market-data freshness."""
    if not snapshot['readable']:
        return 'SOURCE_UNAVAILABLE'
    age = now.astimezone(UTC) - _timestamp(snapshot['checked_utc'])
    if age < timedelta(seconds=-10):
        return 'CLOCK_MISMATCH'
    return 'POLL_RECENT' if age <= timedelta(seconds=15) else 'POLL_STALE'


def synthetic_events() -> list[dict[str, str]]:
    """A fictional illustration of reported records, not actual bot evidence."""
    return [
        {'observed_utc': '2026-10-27T14:30:00Z', 'symbol': 'NVDA', 'strategy': 'GAP_AND_GO',
         'stage': 'DATA_COVERAGE', 'decision': 'PASS', 'reason': 'NOT_RECORDED'},
        {'observed_utc': '2026-10-27T14:30:01Z', 'symbol': 'NVDA', 'strategy': 'GAP_AND_GO',
         'stage': 'QUOTE_HEALTH', 'decision': 'REJECT', 'reason': 'EXCESSIVE_SPREAD'},
        {'observed_utc': '2026-10-27T14:31:00Z', 'symbol': 'AAPL', 'strategy': 'CANDLESTICK',
         'stage': 'LUNCH_CHOP', 'decision': 'REJECT', 'reason': 'LUNCH_CHOP_ZONE'},
    ]
