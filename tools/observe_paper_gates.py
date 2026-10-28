"""Read a user-selected local JSONL gate ledger and write a limited snapshot.

No credentials, broker requests, orders, model requests, or source-file writes.
The operator must inspect the output before sharing or recording it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from auditor.paper_observer import capture_source  # noqa: E402


def write_snapshot(snapshot: dict, target: Path) -> None:
    """Replace only the destination snapshot; do not alter the source ledger."""
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                     prefix='.paper-observation-', delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(snapshot, handle, ensure_ascii=True, separators=(',', ':'))
            handle.write('\n')
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Observe a local paper gate ledger without connecting to a broker.')
    parser.add_argument('--source', required=True, type=Path, help='Path to the existing local JSONL gate ledger')
    parser.add_argument('--confirm-paper-source', action='store_true',
                        help='Attest that the source is a paper-mode ledger; this is not independently verified')
    parser.add_argument('--follow', action='store_true', help='Refresh the sanitized snapshot every five seconds')
    args = parser.parse_args()
    if not args.confirm_paper_source:
        parser.error('You must confirm the source is a paper-mode ledger.')
    if args.source.suffix.lower() != '.jsonl':
        parser.error('The source must be a local .jsonl file.')

    try:
        data_dir = ROOT / 'data'
        if data_dir.is_symlink():
            parser.error('The local data directory must not be a symbolic link.')
        data_dir.mkdir(exist_ok=True)
        target = data_dir / 'paper_gate_observations.json'
        if args.source.resolve() == target.resolve():
            parser.error('Source and output must be different files.')
    except OSError:
        print('Could not prepare the local observation directory.', file=sys.stderr)
        return 1
    print('Paper mode is operator-declared, not verified. Only an allowlisted subset is saved.')
    print('Review the sanitized snapshot locally before sharing. The source file is not modified.')
    try:
        while True:
            doc = capture_source(args.source, checked=datetime.now(timezone.utc))
            write_snapshot(doc, target)
            print(f"Observation: {'readable' if doc['readable'] else 'unavailable'}; "
                  f"{len(doc['events'])} selected events; {doc['ignored_records']} ignored.", flush=True)
            if not args.follow:
                return 0 if doc['readable'] else 1
            time.sleep(5)
    except KeyboardInterrupt:
        print('\nObservation stopped.')
        return 0
    except OSError:
        print('Could not write the local observation snapshot.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
