"""Print bounded, aggregate-only diagnostics for a local paper gate ledger.

This is an independent event-window tool. It neither writes source data nor
contacts a broker or model. Labels are drawn from an explicit finite allowlist;
arbitrary source strings, symbols, identifiers and messages are never printed.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from pathlib import Path
import stat
import sys
from typing import Any


# Field vocabularies, not the implementation of the separate trading bot.
SAFE_REASON_LABELS = frozenset({
    'NOISE_FLOOR', 'CRITICAL_STOP', 'INVALID_STRUCTURAL_STOP', 'INVALID_GEOMETRY',
    'STALE_QUOTE', 'MAX_CHASE', 'EXCESSIVE_SPREAD', 'INVERTED_QUOTE',
    'ZERO_POSITION_SIZE', 'SPY_BEARISH_5M', 'SOXX_TECH_LONG_VETO',
    'COMMODITY_CORRELATION_VETO', 'TECH_CLUSTER_CAP', 'COUNTER_TREND_SHORT_VETO',
    'CONFIDENCE_BELOW_FLOOR', 'LUNCH_CHOP_ZONE', 'RSI_OVERBOUGHT', 'RSI_OVERSOLD',
    'LOW_COVERAGE', 'REGIME_DATA_DEGRADED', 'REGIME_RISK_OFF', 'ENTRY_CUTOFF_TIME',
    'ENTRY_READINESS_FAILED', 'SESSION_COOLDOWN', 'CONSECUTIVE_LOSS_LIMIT',
    'DUPLICATE_ORDER', 'IDEMPOTENCY_HELD', 'STRATEGY_DISABLED', 'TEXTURE_NOT_ALLOWED',
    'NO_SUPPORTED_STRATEGY', 'CANDIDATE_SUPERSEDED', 'ACTIVE_POSITION_UNKNOWN',
    'PRIOR_EXIT_PENDING_RECONCILIATION', 'TEXTURE_RESTRICTION_OVERRIDDEN_FOR_PAPER_EXPERIMENT',
    'ORDER_SUBMITTED', 'REGIME_TEXTURE_FILTER',
})


def summarize(source: Path, observer: Any) -> dict[str, Any]:
    """Match the observer's bounded tail and report only aggregate categories."""
    if source.suffix.lower() != '.jsonl' or not stat.S_ISREG(source.stat().st_mode):
        raise ValueError('Expected a local JSONL file')
    with source.open('rb') as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - observer.MAX_SOURCE_BYTES))
        data = handle.read(observer.MAX_SOURCE_BYTES)
    tail_only = size > observer.MAX_SOURCE_BYTES
    if tail_only:
        data = data.partition(b'\n')[2]
    lines = data.splitlines() if data.endswith(b'\n') else data.splitlines()[:-1]
    dropped = Counter()
    selected: deque[tuple[str, str]] = deque(maxlen=observer.MAX_EVENTS)
    accepted = 0

    for line in lines:
        try:
            raw = observer._json(line.decode('utf-8'))
        except (observer.ObservationError, UnicodeDecodeError):
            dropped['INVALID_JSON_OR_ENCODING'] += 1
            continue
        event = observer.normalize_record(raw)
        if event is None:
            if not isinstance(raw, dict):
                dropped['NOT_AN_OBJECT'] += 1
                continue
            try:
                stamp = observer._timestamp(raw.get('timestamp'))
            except observer.ObservationError:
                dropped['INVALID_OR_MISSING_TIMESTAMP'] += 1
                continue
            if not observer.EVENT_START <= stamp <= observer.EVENT_END:
                dropped['OUTSIDE_EVENT_WINDOW'] += 1
            elif (not isinstance(raw.get('symbol'), str)
                  or not observer.SYMBOL_PATTERN.fullmatch(raw['symbol'])):
                dropped['INVALID_OR_MISSING_SYMBOL'] += 1
            else:
                dropped['OTHER_IGNORED'] += 1
            continue
        accepted += 1
        original_reason = raw.get('reason_code')
        if original_reason in (None, ''):
            label = 'NOT_RECORDED'
        elif isinstance(original_reason, str) and original_reason in SAFE_REASON_LABELS:
            label = original_reason
        else:
            label = 'OTHER_OR_UNKNOWN'
        selected.append((event['decision'], label))

    rejection_counts = Counter(label for decision, label in selected
                               if decision in {'REJECT', 'BLOCK', 'VETO'})
    return {
        'tail_only': tail_only,
        'complete_lines_in_tail': len(lines),
        'accepted_in_tail': accepted,
        'ignored_in_tail': sum(dropped.values()),
        'ignored_categories': dict(sorted(dropped.items())),
        'last_sample_records': len(selected),
        'last_sample_reject_records': sum(rejection_counts.values()),
        'last_sample_reject_reasons': dict(sorted(rejection_counts.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Summarize local gate records without printing raw events.')
    parser.add_argument('--project', required=True, type=Path,
                        help='Path to the existing cockpit candidate folder')
    parser.add_argument('--source', required=True, type=Path,
                        help='Path to the local JSONL gate ledger')
    args = parser.parse_args(argv)
    previous_bytecode = sys.dont_write_bytecode
    project_path = None
    try:
        # The diagnostic should not create Python bytecode in the project folder.
        sys.dont_write_bytecode = True
        project_path = str(args.project.resolve())
        sys.path.insert(0, project_path)
        from auditor import paper_observer
        result = summarize(args.source, paper_observer)
    except (OSError, ValueError, ImportError):
        print('DIAGNOSTIC_UNAVAILABLE: Check the project and source paths locally.')
        return 1
    finally:
        sys.dont_write_bytecode = previous_bytecode
        if project_path is not None and sys.path and sys.path[0] == project_path:
            sys.path.pop(0)
    print('AGGREGATE COUNTS ONLY. No raw records, symbols, account IDs, or credentials are printed.')
    print('The counts reflect one bounded read; they may differ from the live dashboard snapshot.')
    print('Tail only:', result['tail_only'])
    print('Complete lines in sampled tail:', result['complete_lines_in_tail'])
    print('Accepted lines in sampled tail:', result['accepted_in_tail'])
    print('Ignored lines in sampled tail:', result['ignored_in_tail'])
    print('Ignored categories:')
    for label, count in result['ignored_categories'].items():
        print(f'  {label}: {count}')
    print('Recent sample records:', result['last_sample_records'])
    print('Recent sample reject/block records:', result['last_sample_reject_records'])
    print('Recent sample rejection reasons (fixed allowlist; remaining values grouped):')
    for label, count in result['last_sample_reject_reasons'].items():
        print(f'  {label}: {count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
