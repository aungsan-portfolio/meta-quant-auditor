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
from auditor.model_json import strict_json_object, unwrap_json_response


def json_failure_diagnostic(text: str) -> dict | None:
    """Classify a rejected envelope without retaining or returning model text.

    This only observes the response already received. It does not repair the
    response, relax the parser, call the provider again, or execute an action.
    The receipt contains fixed labels rather than error messages or excerpts.
    """
    if type(text) is not str:
        return {'error': 'NOT_TEXT', 'prefix': 'OTHER'}
    stripped = text.strip()
    prefix = ('OBJECT' if stripped.startswith('{') else
              'FENCE' if stripped.startswith('```') else 'OTHER')
    if not stripped or len(text) > 12_000:
        return {'error': 'EMPTY_OR_OVERSIZED', 'prefix': prefix}
    try:
        body = unwrap_json_response(text)
        strict_json_object(text)
    except json.JSONDecodeError as exc:
        position = ('START' if exc.pos <= 1 else
                    'END' if exc.pos >= max(0, len(body) - 2) else 'MIDDLE')
        code = 'EXTRA_CONTENT' if exc.msg == 'Extra data' else 'JSON_SYNTAX'
        return {'error': code, 'prefix': prefix, 'position': position}
    except ValueError as exc:
        codes = {'Unsupported JSON response envelope.': 'INVALID_FENCE',
                 'Duplicate JSON property.': 'DUPLICATE_KEY',
                 'Nonfinite JSON number.': 'NONFINITE_NUMBER',
                 'JSON object required.': 'NOT_OBJECT',
                 'Empty or oversized JSON response.': 'EMPTY_OR_OVERSIZED'}
        return {'error': codes.get(str(exc), 'INVALID_JSON'), 'prefix': prefix}
    except (TypeError, RecursionError, OverflowError):
        return {'error': 'INVALID_JSON', 'prefix': prefix}
    return None


def run_spike(api_key: str, *, transport=None) -> dict:
    receipt = {'model': MODEL, 'protocol': 'json-action-v1', 'synthetic': True,
               'status': 'NOT_RUN', 'reason': 'KEY_MISSING', 'cases': []}
    if not api_key or not api_key.strip() or api_key.strip() == 'your_baseten_api_key_here':
        return receipt
    started = time.monotonic()
    for scenario in ('late_fill', 'order_unavailable'):
        run = AgentRun(scenario)
        diagnostic = None
        def ask(context):
            nonlocal diagnostic
            if time.monotonic() - started >= 600:
                raise TimeoutError('Spike window ended.')
            text = request_action(context, api_key, transport=transport)
            try:
                diagnostic = json_failure_diagnostic(text)
            except Exception:
                # Diagnostics must never alter the actual validation or leak text.
                diagnostic = {'error': 'DIAGNOSTIC_FAILED', 'prefix': 'OTHER'}
            return text
        result = run.run(ask)
        actions = [s['action'] for s in result['steps']]
        correct = (result['status'] == 'FINISHED' if scenario == 'late_fill'
                   else result['status'] == 'NEEDS_INPUT' and 'query_order_status' in actions)
        case = {'scenario': scenario, 'status': result['status'],
                'reason': result['reason'], 'actions': actions,
                'protocol_and_path_ok': correct}
        if result['reason'] == 'MALFORMED_JSON' and diagnostic is not None:
            case['json_diagnostic'] = diagnostic
        receipt['cases'].append(case)
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
