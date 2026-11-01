"""Run explicitly consented, independent synthetic agent trials.

Each trial is a new run; a failed action is never retried within that run. The
receipt records every planned attempt, including failures and unavailable calls,
without API keys, model prose, or private data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auditor.model import MODEL
from tools.run_agent_spike import run_case

SCENARIOS = ('late_fill', 'order_unavailable')
WINDOW_SECONDS = 600.0


def source_state() -> dict:
    """Return only a commit and clean flag; never expose paths or git output."""
    try:
        head = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=ROOT,
                              capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=5, check=True).stdout.strip()
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=5, check=True).stdout
        return {'commit': head if re.fullmatch(r'[0-9a-f]{40}', head) else None,
                'working_tree_clean': not bool(status.strip())}
    except (OSError, subprocess.SubprocessError):
        return {'commit': None, 'working_tree_clean': None}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def run_reliability(api_key: str, *, runs_per_case: int = 3, transport=None, on_progress=None) -> dict:
    if type(runs_per_case) is not int or runs_per_case not in (3, 4, 5):
        raise ValueError('Choose 3, 4 or 5 planned runs per scenario.')
    start_source = source_state()
    receipt = {'model_requested': MODEL, 'provider_configured': 'Baseten',
               'synthetic': True, 'protocol': 'json-action-v1', 'started_at_utc': utc_now(),
               'source_at_start': start_source, 'runs_per_case_planned': runs_per_case,
               'status': 'NOT_RUN', 'reason': 'KEY_MISSING', 'runs': []}
    if not isinstance(api_key, str) or not api_key.strip() or api_key.strip() == 'your_baseten_api_key_here':
        return receipt
    started = time.monotonic()
    deadline = started + WINDOW_SECONDS
    for repetition in range(1, runs_per_case + 1):
        for scenario in SCENARIOS:
            if time.monotonic() + 30.0 >= deadline:
                break
            case_started = utc_now()
            case = run_case(scenario, api_key, transport=transport, deadline=deadline)
            case['repetition'] = repetition
            case['started_at_utc'] = case_started
            case['finished_at_utc'] = utc_now()
            receipt['runs'].append(case)
            if on_progress:
                on_progress({'repetition': repetition, 'scenario': scenario,
                             'status': case['status'], 'protocol': case['protocol'],
                             'protocol_and_path_ok': case['protocol_and_path_ok']})
        else:
            continue
        break
    counts = {}
    for scenario in SCENARIOS:
        results = [case for case in receipt['runs'] if case['scenario'] == scenario]
        counts[scenario] = {
            'planned': runs_per_case,
            'attempted': len(results),
            'protocol_compliant': sum(case['protocol'] == 'COMPLIANT' for case in results),
            'protocol_violation': sum(case['protocol'] == 'VIOLATION' for case in results),
            'protocol_incomplete': sum(case['protocol'] == 'INCOMPLETE' for case in results),
            'protocol_undetermined': sum(case['protocol'] == 'UNDETERMINED' for case in results),
            'expected_path_pass': sum(case['protocol_and_path_ok'] for case in results),
        }
    all_steps = [step for case in receipt['runs'] for step in case['steps']]
    receipt['finished_at_utc'] = utc_now()
    receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
    receipt['source_at_end'] = source_state()
    start_commit = receipt['source_at_start']['commit']
    end_commit = receipt['source_at_end']['commit']
    receipt['git_head_unchanged'] = (start_commit == end_commit) if start_commit and end_commit else None
    receipt['summary'] = counts
    receipt['observed_response_origin'] = ('BASETEN_LIVE_RESPONSE' if all_steps and all(
        step['response_source'] == 'BASETEN_LIVE_RESPONSE' for step in all_steps)
        else 'UNVERIFIED_OR_CUSTOM')
    complete = (all(counts[scenario]['attempted'] == runs_per_case for scenario in SCENARIOS)
                and not any(case.get('window_ended') for case in receipt['runs']))
    receipt['status'] = 'COMPLETE' if complete else 'INCOMPLETE'
    receipt['reason'] = 'PLANNED_RUNS_COMPLETED' if complete else 'TIME_WINDOW_ENDED'
    receipt['all_protocol_compliant'] = complete and all(
        item['protocol_compliant'] == runs_per_case for item in counts.values())
    receipt['all_expected_paths_passed'] = complete and all(
        item['expected_path_pass'] == runs_per_case for item in counts.values())
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--consent', action='store_true', help='Send fictional scenarios to Baseten for each planned run.')
    parser.add_argument('--runs-per-case', type=int, choices=(3, 4, 5), default=3)
    parser.add_argument('--output', type=Path, required=True, help='New receipt file, e.g. reports/agent-reliability.json.')
    args = parser.parse_args(argv)
    if not args.consent:
        parser.error('--consent is required for live requests')
    if args.output.exists():
        parser.error('Output file already exists; choose a new filename.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)

    def progress(case):
        print(f"Run {case['repetition']} | {case['scenario']} | {case['status']} | "
              f"protocol {case['protocol']} | expected path {case['protocol_and_path_ok']}", flush=True)

    receipt = run_reliability(os.environ.get('BASETEN_API_KEY', '').strip(),
                              runs_per_case=args.runs_per_case, on_progress=progress)
    text = json.dumps(receipt, indent=2, allow_nan=False)
    print(text)
    with args.output.open('x', encoding='utf-8') as output:
        output.write(text + '\n')
    if receipt['status'] != 'COMPLETE':
        return 2
    return 0 if receipt['all_expected_paths_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
