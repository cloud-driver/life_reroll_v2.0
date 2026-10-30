"""Keep public HTTP payloads aligned with the delivered schema reference."""

from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
from . import content

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / 'data/schema_reference.json').read_text(encoding='utf-8'))[
    '$defs'
]


def date_index(index):
    return f'{2026 + index // 12:04d}-{index % 12 + 1:02d}-01' if index is not None else None


def adapt(name, value):
    if value is None:
        return None
    v = value.copy() if isinstance(value, dict) else value
    if not isinstance(v, dict):
        return v
    if name == 'Bootstrap':
        v.update(maintenance=False, notice=None, max_runs=3, stock_count=5)
        v['email_verification_required'] = not v.get('development_email_bypass', False)
    elif name == 'Session':
        v['csrf_token'] = v.get('csrf_token') or ''
        v['expires_at'] = (
            None
            if not v.get('user')
            else v.get('expires_at') or (datetime.now().astimezone() + timedelta(days=30)).isoformat()
        )
    elif name == 'Settings':
        v = {
            'locale': 'zh-TW',
            'sound_enabled': v.get('music', v.get('sound_enabled', True)),
            'reduced_motion': v.get('reduced_motion', False),
            'text_scale': v.get('text_scale', 1.0),
            'tutorial_completed': v.get('tutorial_completed', v.get('tutorial_complete', False)),
        }
    elif name == 'DeviceSession':
        v['device_label'] = '目前裝置' if v.get('current') else '其他裝置'
        v['last_seen_at'] = v.get('created_at')
        v['is_current'] = v.get('current', False)
    elif name == 'LedgerEntry':
        # Saved ledgers may omit the optional-in-storage counterpart. Do not
        # invent an account or rewrite historical transactions when reading.
        v['counter_account'] = v.get('counter_account') or ''
    elif name == 'Campaign':
        v['current_run_id'] = v.get('current_run_id')
        v['run_count'] = len(v.get('run_ids', []))
        v['ruleset_version'] = content.CONTENT_VERSION
        v['job_id'] = None
    elif name == 'RunState':
        p = v.get('persona') or {}
        start = v.get('start_age', v.get('age', 25))
        events = v.get('events', [])
        v['sim_date'] = v.get('current_date') or date_index(v.get('month_index', 0))
        v['balances']['negative_years'] = v.get('negative_years', 0)
        v['balances']['negative_since'] = (
            None
            if v['balances']['negative_years'] == 0
            else f'{2026 + (v.get("month_index", 0) // 12) - v["balances"]["negative_years"]:04d}-01-01'
        )
        v['campaign_id'] = v.get('campaign_id') or 'no-campaign'
        v['character'] = {
            'id': p.get('id', 'unknown'),
            'name': p.get('occupation', '角色') + '的人生',
            'birth_date': f'{2026 - start:04d}-01-01',
            'starting_age': start,
            'occupation': v.get('current_occupation', p.get('occupation', '未知')),
            'employment_status': v.get('employment_status', 'EMPLOYED'),
            'monthly_salary_minor': v.get('salary_minor', 0),
            'household': {
                'marital_status': 'MARRIED'
                if any(x.get('card_id') == 'FA15' and x['status'] != 'PENDING' for x in events)
                else 'SINGLE',
                'dependents': sum(1 for x in events if x.get('card_id') == 'FA12' and x['status'] != 'PENDING'),
                'monthly_support_minor': v.get('support_minor', 0),
                'beneficiary_label': '家人',
            },
            'health_tags': [p.get('family_history', '無病史')],
            'background': f'{p.get("industry", "")}，通勤：{p.get("commute_mode", "")}。家族病史為背景資訊，不代表確診。',
        }
        v['advance_id'] = (v.get('advance') or {}).get('id')
        v['event_stack'] = [v['pending_event_id']] if v.get('pending_event_id') else []
        v['end_reason'] = v.get('end_reason') or 'NONE'
        v['ruleset_version'] = content.CONTENT_VERSION
        v['allowed_actions'] = [
            {'action': action, 'enabled': True, 'reason_code': None, 'message': None}
            for action in v.get('allowed_actions', [])
        ]
    elif name == 'Balances':
        v['term_principal_minor'] = v.get('term_principal_minor', v.get('term_minor', 0))
        v['stocks_market_value_minor'] = v.get('stocks_market_value_minor', v.get('stocks_minor', 0))
        v['policy_cash_value_minor'] = v.get('policy_cash_value_minor', 0)
        v['receivables_minor'] = v.get('receivables_minor', 0)
        v['liabilities_minor'] = v.get('liabilities_minor', v.get('loan_minor', 0) + v.get('bill_minor', 0))
        v['immediate_liquidity_minor'] = v.get('cash_minor', 0) + v.get('savings_minor', 0)
        v['negative_since'] = v.get('negative_since')
        v['negative_years'] = v.get('negative_years', 0)
    elif name == 'Advance':
        v['current_date'] = v.get('current_date', v['from_date'])
        v['remaining_days'] = v.get('remaining_days', v.get('remaining_months', 0) * 30)
        v['summary'] = v.get('summary')
    elif name == 'Event':
        v['kind'] = {'TRAVEL': 'EXPENSE', 'LIFE': 'FAMILY'}.get(v['kind'], v['kind'])
        v['learning_topic_ids'] = v.get('learning_topic_ids', [])
        v['visual_key'] = v.get('visual_key') or v.get('card_id')
    elif name == 'Choice':
        v['description'] = v.get('description', v['label'])
        v['enabled'] = v.get('enabled', True)
        v['disabled_reason'] = v.get('disabled_reason')
        v['requires_confirmation'] = v.get('requires_confirmation', False)
        v['estimated_cash_cost_minor'] = v.get('estimated_cash_cost_minor')
    elif name == 'EventOutcome':
        v['ledger_entry_ids'] = v.get('ledger_entry_ids', [])
        v['claim_ids'] = v.get('claim_ids', [])
        v['learning_message'] = v.get('learning_message', '依當時實際預算、保障與生活品質綜合檢視。')
    elif name == 'Stock':
        v['risk_level'] = 'LOW' if v['id'] == 'STABLE' else 'HIGH' if v['id'] in ('TECH', 'GREEN') else 'MEDIUM'
        v['description'] = v.get('description', f'虛構{v.get("sector", "")}產業股票，報酬不保證。')
    elif name == 'Scene':
        v['asset_key'] = v.get('asset_key', v['id'].lower())
        v['entry_spawn'] = v.get('entry_spawn', 'door')
    elif name == 'Lesson':
        v['source_urls'] = v.get('source_urls', [])
        v['related_product_ids'] = v.get('related_product_ids', [])
        v['version'] = content.CONTENT_VERSION
    elif name == 'InsuranceProduct':
        p = content.PRODUCT_BY_ID.get(v.get('id'), v)
        v['source_checked_on'] = None
        v['premium_rule_summary'] = f'虛構費率年繳 {p.get("premium_rate_bps", 0)} 基點；高年齡調整詳報價。'
        v['claim_payment_delay_days'] = p.get('claim_delay_months', 0) * 30
        v['renewal_summary'] = '每年繳費；寬限期後可失效。'
        v['surrender_summary'] = '本期教學商品無解約金。'
    elif name == 'BenefitRule':
        v['trigger_summary'] = v.get('trigger_summary', '限符合所列事件及等待期的遊戲內損失。')
        v['coordination_rule'] = v.get('coordination_rule', '核實費用不超過實際支出；定額給付單獨計。')
    elif name == 'Policy':
        v['coverage_from'] = date_index(v.get('coverage_from_index'))
        v['coverage_until'] = v.get('coverage_until')
        v['next_premium_on'] = date_index(v.get('next_premium_index'))
        v['reinstatement_available'] = v.get('status') == 'LAPSED'
    elif name == 'Claim':
        v['payable_on'] = date_index(v.get('payable_index'))
    elif name == 'FundingOption':
        v['resource_id'] = v.get('resource_id')
        v['available_on'] = v.get('available_on')
        v['reason'] = v.get('reason')
    elif name == 'Holding':
        v['unrealized_pnl_minor'] = v['market_value_minor'] - v['cost_basis_minor']
    elif name == 'TermDeposit':
        v['matures_on'] = date_index(v.get('matures_index'))
    elif name == 'Loan':
        v['outstanding_principal_minor'] = v.get('principal_minor', 0)
        v['accrued_interest_minor'] = v.get('interest_minor', 0)
        v['next_due_minor'] = min(
            v.get('principal_minor', 0), v.get('original_minor', 0) // max(1, v.get('term_months', 1))
        ) + v.get('interest_minor', 0)
    elif name == 'ScoreDimension':
        v['confidence'] = v.get('confidence', 'MEDIUM')
        v['score'] = v.get('score')
    elif name == 'CoverageEffect':
        v['explanation'] = v.get('explanation', '分別記錄保費、實際核付與自行負擔。')
    elif name == 'RunReport':
        v['inherited_prefix_until'] = v.get('inherited_prefix_until')
    elif name == 'Job':
        v['type'] = {'REBIRTH': 'REBIRTH_PLAN', 'DELETE_ACCOUNT': 'ACCOUNT_ERASURE'}.get(v['type'], v['type'])
        v['progress_percent'] = v.get('progress_percent', 100 if v['status'] == 'SUCCEEDED' else 0)
        v['stage'] = v.get('stage', '已完成' if v['status'] == 'SUCCEEDED' else '排隊中')
    elif name == 'Notice':
        v['read_at'] = v.get('read_at')
        v['resource'] = v.get('resource')
    elif name == 'AuditEntry':
        v['resource_id'] = v.get('resource_id', v['id'])
        v['summary'] = v.get('summary', v['action'])
    elif name == 'ContentRelease':
        v['persona_count'] = v.get('persona_count', 0)
        v['stock_count'] = v.get('stock_count', 5)
        v['product_count'] = v.get('product_count', 0)
    elif name == 'ResourceRef':
        v['href'] = v.get('href', '/api/v1/')
    return v


def schema_value(schema, value):
    if value is None:
        return None
    if '$ref' in schema:
        return shape(schema['$ref'].rsplit('/', 1)[-1], value)
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            if option.get('type') != 'null':
                return schema_value(option, value)
    if schema.get('type') == 'array':
        return [schema_value(schema.get('items', {}), x) for x in value]
    if schema.get('type') == 'object' and isinstance(value, dict):
        return {
            k: schema_value(schema['properties'][k], x) for k, x in value.items() if k in schema.get('properties', {})
        }
    return value


def shape(name, value):
    if value is None:
        return None
    base = adapt(name, value)
    fields = SCHEMA[name].get('properties', {})
    obj = {k: schema_value(fields[k], v) for k, v in base.items() if k in fields}
    missing = SCHEMA[name].get('required', [])
    for key in missing:
        if key not in obj:
            raise ValueError(f'WIRE_MISSING_{name}_{key}')
    return obj


def output(item, value):
    if value is None:
        return None
    name = item['output'].split(' ', 1)[-1]
    if name == '—':
        return None
    if name.startswith('Page<'):
        inner = name[5:-1]
        return {
            'items': [shape(inner, x) for x in value['items']],
            'next_cursor': value.get('next_cursor'),
            'total': value.get('total', len(value['items'])),
        }
    if name.endswith('[]'):
        return [shape(name[:-2], x) for x in value]
    if name.endswith('?'):
        name = name[:-1]
    if name in SCHEMA:
        return shape(name, value)
    return value
