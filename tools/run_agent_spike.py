"""Explicit-consent, at-most-ten-minute protocol spike; never prints credentials.

Run from the repository: python tools/run_agent_spike.py --consent
Receipts contain statuses/action names, not model prose or request headers.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from auditor.agent import AgentRun
from auditor.agent_model import request_action
from auditor.model import MODEL


def run_spike(api_key: str, *, transport=None) -> dict:
    receipt = {'model': MODEL, 'protocol': 'json-action-v1', 'synthetic': True,
               'status': 'NOT_RUN', 'reason': 'KEY_MISSING', 'cases': []}
    if not api_key or not api_key.strip() or api_key.strip() == 'your_baseten_api_key_here':
        return receipt
    started = time.monotonic()
    for scenario in ('late_fill', 'order_unavailable'):
        run = AgentRun(scenario)
        def ask(context):
            if time.monotonic() - started >= 600:
                raise TimeoutError('Spike window ended.')
            return request_action(context, api_key, transport=transport)
        result = run.run(ask)
        actions = [s['action'] for s in result['steps']]
        correct = (result['status'] == 'FINISHED' if scenario == 'late_fill'
                   else result['status'] == 'NEEDS_INPUT' and 'query_order_status' in actions)
        receipt['cases'].append({'scenario': scenario, 'status': result['status'],
                                 'reason': result['reason'], 'actions': actions,
                                 'protocol_and_path_ok': correct})
        if not correct:
            break  # No repair call, automatic retry, or second-case rescue.
    receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
    receipt['status'] = 'GO_PROTOCOL' if len(receipt['cases']) == 2 and all(
        c['protocol_and_path_ok'] for c in receipt['cases']) else 'NO_GO'
    receipt['reason'] = 'TWO_SCRIPTED_PATHS_CHECKED' if receipt['status'] == 'GO_PROTOCOL' else 'INSPECT_FAILED_PATH'
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--consent', action='store_true', help='Send only built-in synthetic facts to Baseten.')
    parser.add_argument('--output', type=Path, help='Optional local receipt, e.g. reports/agent-spike.json.')
    args = parser.parse_args(argv)
    if not args.consent:
        parser.error('--consent is required for live requests')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    receipt = run_spike(os.environ.get('BASETEN_API_KEY', '').strip())
    text = json.dumps(receipt, indent=2, allow_nan=False)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + '\n', encoding='utf-8')
    return 0 if receipt['status'] == 'GO_PROTOCOL' else 2


if __name__ == '__main__':
    raise SystemExit(main())
