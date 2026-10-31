"""Bounded JSON-action auditor over built-in FICTIONAL lifecycle scenarios.

The model selects actions; only local code constructs observations, audit gates,
claim comparisons and reports. There is no broker, filesystem or shell tool.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import json
from typing import Callable

from .cancellation import audit_trace, model_evidence, parse_trace, sample_traces
from .claims import ClaimsError, verify_claims
from .followup import append_followup, evidence_request
from .model_json import strict_json_object
from .review import build_memo


MAX_STEPS = 8
OUTPUT_INSTRUCTION = (
    'Choose the next allowed action for this fictional case. Return one JSON object '
    'with exactly action, args, and reason. Do not add any text outside the object.'
)
ACTIONS = frozenset({'run_lifecycle_audit', 'query_order_status', 'query_position',
                     'query_protection', 'compare_claims', 'request_human_input', 'finish_report'})
SCENARIOS = {
    'late_fill': 'Late fill · scripted position and protection available',
    'order_recovered': 'Unknown order · scripted cancellation confirmation available',
    'order_unavailable': 'Unknown order · order snapshot unavailable',
    'position_unavailable': 'Late fill · position snapshot unavailable',
    'protection_unavailable': 'Late fill · protection snapshot unavailable',
}
QUERY_KINDS = {'query_order_status': 'BROKER_ORDER', 'query_position': 'POSITION_OBSERVED',
               'query_protection': 'PROTECTION_OBSERVED'}


class ActionError(ValueError):
    """Protocol/argument error; never include untrusted response text."""


@dataclass(frozen=True)
class Action:
    action: str
    args: dict
    reason: str


def parse_action(text: str) -> Action:
    try:
        obj = strict_json_object(text)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ActionError('MALFORMED_JSON') from None
    if set(obj) != {'action', 'args', 'reason'}:
        raise ActionError('INVALID_SCHEMA')
    if type(obj['action']) is not str or obj['action'] not in ACTIONS:
        raise ActionError('INVALID_ACTION')
    if type(obj['args']) is not dict:
        raise ActionError('INVALID_ARGS')
    if type(obj['reason']) is not str or not 1 <= len(obj['reason'].strip()) <= 500:
        raise ActionError('INVALID_REASON')
    return Action(obj['action'], obj['args'], obj['reason'].strip())


def _scenario(scenario_id: str):
    if type(scenario_id) is not str or scenario_id not in SCENARIOS:
        raise ValueError('Unknown built-in agent scenario.')
    source = sample_traces()['Broker query unavailable' if scenario_id.startswith('order_')
                             else 'Pending cancel → early release → late fill']
    snapshots = {
        'query_order_status': {'status': 'CANCELED', 'cumulative_fill': 0.0},
        'query_position': {'position_qty': 4.0},
        'query_protection': {'status': 'ACTIVE', 'coverage_qty': 4.0},
    }
    if scenario_id.endswith('_unavailable'):
        snapshots[{'order_unavailable': 'query_order_status',
                   'position_unavailable': 'query_position',
                   'protection_unavailable': 'query_protection'}[scenario_id]] = None
    return json.dumps(source, allow_nan=False), snapshots


class AgentRun:
    """One serial, at-most-eight-step run. Only built-in scenario IDs accepted."""
    def __init__(self, scenario_id: str, *, max_steps: int = MAX_STEPS):
        if type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS:
            raise ValueError('Step limit must be an integer from 1 through 8.')
        self.scenario_id = scenario_id
        self._raw, self._scripted = _scenario(scenario_id)
        self._report = audit_trace(parse_trace(self._raw))
        self.max_steps = max_steps
        self.status = 'RUNNING'
        self.reason = 'READY'
        self._steps = []
        self._used = set()
        self._audited = False
        self._final = None

    def context(self) -> dict:
        # Never feed model-generated reason/narrative back as trusted evidence.
        return deepcopy({
            'synthetic': True, 'scenario_id': self.scenario_id,
            'evidence': model_evidence(self._report),
            'missing_evidence': asdict(evidence_request(self._report)),
            'audit_action_completed': self._audited,
            'used_actions': sorted(self._used),
            'remaining_steps': self.max_steps - len(self._steps),
            'output_instruction': OUTPUT_INSTRUCTION,
            'observations': [{'action': s['action'], 'tool_output': s['tool_output']}
                             for s in self._steps if s['validation'] == 'ALLOWED'],
        })

    def snapshot(self) -> dict:
        return deepcopy({'scenario_id': self.scenario_id, 'synthetic': True,
                         'status': self.status, 'reason': self.reason,
                         'max_steps': self.max_steps, 'steps': self._steps,
                         'local_memo': build_memo(self._report), 'final_report': self._final})

    def scripted_snapshots(self) -> dict:
        """Consent preview of all fixed observations a query can reveal."""
        return deepcopy(self._scripted)

    def stop(self, status: str, reason: str) -> None:
        if self.status == 'RUNNING':
            self.status, self.reason = status, reason

    def _claims(self, args: dict, *, final: bool):
        expected = {'claims', 'narrative'} if final else {'claims'}
        if set(args) != expected:
            raise ActionError('INVALID_ARGS')
        narrative = args.get('narrative', '')
        if type(narrative) is not str or len(narrative) > 4000:
            raise ActionError('INVALID_ARGS')
        try:
            return verify_claims(self._report, json.dumps(
                {'claims': args['claims'], 'interpretation': narrative}, allow_nan=False))
        except (ClaimsError, ValueError, TypeError, RecursionError, OverflowError):
            raise ActionError('INVALID_ARGS') from None

    def step(self, response: str) -> dict:
        if self.status != 'RUNNING':
            raise ValueError('Agent run already ended.')
        if len(self._steps) >= self.max_steps:
            self.stop('STEP_LIMIT', 'STEP_LIMIT')
            return self.snapshot()
        proposal = None
        validation, output = 'REJECTED', {}
        try:
            proposal = parse_action(response)
            name, args = proposal.action, proposal.args
            if name in self._used:
                raise ActionError('REPEATED_ACTION')
            if name not in {'compare_claims', 'finish_report'} and args:
                raise ActionError('INVALID_ARGS')
            checked = self._claims(args, final=name == 'finish_report') if name in {
                'compare_claims', 'finish_report'} else None
            if name != 'run_lifecycle_audit' and not self._audited:
                raise ActionError('AUDIT_REQUIRED')
            missing = evidence_request(self._report)
            if name in QUERY_KINDS and (missing.status != 'NEEDS_INPUT'
                                       or missing.event_type != QUERY_KINDS[name]):
                raise ActionError('QUERY_NOT_REQUIRED')
            self._used.add(name)
            validation = 'ALLOWED'
            if name == 'run_lifecycle_audit':
                self._report = audit_trace(parse_trace(self._raw))
                self._audited = True
                output = {'source': 'LOCAL_DETERMINISTIC_AUDIT',
                          'memo': build_memo(self._report),
                          'missing_evidence': asdict(evidence_request(self._report))}
            elif name in QUERY_KINDS:
                scripted = self._scripted[name]
                if scripted is None:
                    output = {'source': 'SCRIPTED_FICTIONAL_SNAPSHOT', 'availability': 'unavailable'}
                    self.stop('NEEDS_INPUT', 'SCRIPTED_EVIDENCE_UNAVAILABLE')
                else:
                    # No model-supplied values can enter the fictional trace.
                    updated = append_followup(self._report, deepcopy(scripted))
                    self._report = audit_trace(parse_trace(updated))
                    self._raw = updated
                    output = {'source': 'SCRIPTED_FICTIONAL_SNAPSHOT', 'availability': 'available',
                              'snapshot': scripted, 'appended_event_id': self._report.events[-1].event_id,
                              'local_memo': build_memo(self._report),
                              'missing_evidence': asdict(evidence_request(self._report))}
            elif name == 'request_human_input':
                output = {'source': 'LOCAL_EVIDENCE_REQUEST', 'request': asdict(missing)}
                self.stop('NEEDS_INPUT', 'HUMAN_INPUT_REQUESTED')
            elif name == 'compare_claims':
                output = {'source': 'LOCAL_CLAIM_VERIFIER',
                          'claims': [asdict(c) for c in checked.claims]}
            elif name == 'finish_report':
                if missing.status == 'NEEDS_INPUT':
                    output = {'source': 'LOCAL_EVIDENCE_REQUEST', 'request': asdict(missing)}
                    self.stop('NEEDS_INPUT', 'MISSING_EVIDENCE')
                else:
                    self._final = {'synthetic': True, 'local_memo': build_memo(self._report),
                                   'claims': [asdict(c) for c in checked.claims],
                                   'narrative_unverified': checked.interpretation,
                                   'review_required': missing.status == 'REVIEW_REQUIRED'
                                   or any(c.status != 'EVIDENCE_MATCH' for c in checked.claims)}
                    output = self._final
                    self.stop('FINISHED', 'REPORT_REQUIRES_HUMAN_REVIEW')
        except ActionError as exc:
            output = {'error': str(exc)}
            self.stop('REJECTED', str(exc))
        except Exception:
            output = {'error': 'LOCAL_TOOL_ERROR'}
            self.stop('REJECTED', 'LOCAL_TOOL_ERROR')
        self._steps.append({'step': len(self._steps) + 1,
                            'action': proposal.action if proposal else 'INVALID',
                            'args': deepcopy(proposal.args) if proposal else {},
                            'reason_unverified': proposal.reason if proposal else '',
                            'validation': validation, 'tool_output': deepcopy(output)})
        if self.status == 'RUNNING' and len(self._steps) >= self.max_steps:
            self.stop('STEP_LIMIT', 'STEP_LIMIT')
        return self.snapshot()

    def run(self, requester: Callable[[dict], str], *, on_update=None, cancelled=None) -> dict:
        """One response per step, strictly serial, no retries or repair calls."""
        while self.status == 'RUNNING':
            if cancelled and cancelled():
                self.stop('CANCELLED', 'OPERATOR_STOPPED')
                break
            try:
                response = requester(self.context())
            except Exception:
                self.stop('MODEL_UNAVAILABLE', 'MODEL_REQUEST_FAILED')
                break
            if cancelled and cancelled():
                self.stop('CANCELLED', 'OPERATOR_STOPPED')
                break
            self.step(response)
            if on_update:
                on_update(self.snapshot())
        result = self.snapshot()
        if on_update:
            on_update(result)
        return result
