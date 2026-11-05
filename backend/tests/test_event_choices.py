"""Event choices must each lead somewhere: a real cost, a real trade, or an honest news item."""

import copy

import pytest

from app import content, engine, event_choices, wire


def fire(card_id, *, cash=None, holdings=None, salary=None):
    r = engine.create_run(content.PERSONAS[0], 7)
    if cash is not None:
        r['balances'] = {'cash_minor': cash, 'savings_minor': 0}
    if holdings is not None:
        r['holdings'] = dict(holdings)
        r['holding_cost_minor'] = {sid: qty * r['prices'][sid] for sid, qty in holdings.items()}
    if salary is not None:
        r['salary_minor'] = salary
    r['planned'] = [{'at_index': 1, 'card_id': card_id, 'anchor': False}]
    r['status'] = 'ADVANCING'
    r['target_index'] = 12
    r['advance'] = {'id': 'test', 'from_date': engine.sim_date(r)}
    engine.next_step(r)
    assert r['status'] == 'EVENT_PENDING'
    return r, r['events'][-1]


def choose(r, e, choice_id):
    engine.decide(r, e['id'], choice_id)
    return next(c for c in e['choices'] if c['id'] == choice_id)


def liquid(r):
    return r['balances']['cash_minor'] + r['balances']['savings_minor']


def test_every_event_has_a_consequence_or_is_news():
    keys = ('cash_delta_minor', 'quality_delta', 'salary_change_bps', 'monthly_cost_delta_minor', 'market_shock_bps')
    idle = [
        card['id']
        for card in content.EVENTS
        if not card.get('choice_model')
        and not any(card['effect'][k] for k in keys)
        and card['id'] not in ('CH08', 'CR03', 'CR04', 'FA12', 'FA04')  # handled explicitly in engine.decide
    ]
    assert idle == []
    assert set(content.EVENT_CHOICE_MODELS) <= set(content.EVENT_BY_ID)


@pytest.mark.parametrize('card_id', ['FA21', 'FA22', 'FA23', 'FA27'])
def test_cost_choices_differ_and_never_exceed_55_percent_of_assets(card_id):
    r, e = fire(card_id, cash=100_000_000, holdings={})
    assets = event_choices.total_assets(r)
    costs = [c['estimated_cash_cost_minor'] for c in e['choices']]
    assert len(set(costs)) == 3 and max(costs) <= assets * 55 // 100
    assert all(c['impacts'] and c['impacts'][0].startswith('一次支出') for c in e['choices'])

    poor, pe = fire(card_id, cash=20_000_000, holdings={})
    cap = event_choices.total_assets(poor) * 55 // 100
    priciest = max(pe['choices'], key=lambda c: c['cost_minor'])
    assert priciest['estimated_cash_cost_minor'] == cap
    assert all(any('55%' in line for line in c['impacts']) for c in pe['choices'])
    # Scaled, not clipped: the options keep their order and stay distinct.
    ordered = sorted(pe['choices'], key=lambda c: c['cost_minor'])
    scaled = [c['estimated_cash_cost_minor'] for c in ordered]
    assert scaled == sorted(scaled) and len(set(scaled)) == 3
    before = liquid(poor)
    choose(poor, pe, priciest['id'])
    assert before - liquid(poor) == cap
    assert pe['outcome']['cash_delta_minor'] == -cap


def test_career_raise_is_fixed_and_choice_sets_lifestyle():
    results = {}
    for choice_id in ('SAVE', 'HALF', 'LIFESTYLE'):
        r, e = fire('CH07', salary=6_000_000)
        living, quality = r['living_minor'], r['quality']
        choose(r, e, choice_id)
        results[choice_id] = (r['salary_minor'], r['living_minor'] - living, r['quality'] - quality)
    raise_minor = 6_000_000 * 1200 // 10000
    assert {v[0] for v in results.values()} == {6_000_000 + raise_minor}
    assert [results[k][1] for k in ('SAVE', 'HALF', 'LIFESTYLE')] == [0, raise_minor // 2, raise_minor]
    assert [results[k][2] for k in ('SAVE', 'HALF', 'LIFESTYLE')] == [0, 2, 4]


def test_market_shock_without_holdings_is_news_and_still_moves_the_market():
    r, e = fire('CH01', holdings={})
    assert [c['id'] for c in e['choices']] == ['ACK']
    assert '沒有持股' in e['choices'][0]['impacts'][0]
    choose(r, e, 'ACK')
    assert r['market_residual'] == -700


def test_market_shock_choices_trade_real_holdings():
    holdings = {'TECH': 400, 'STABLE': 300}
    r, e = fire('CH14', cash=50_000_000, holdings=holdings)
    by_id = {c['id']: c for c in e['choices']}
    assert set(by_id) == {'HOLD', 'REDUCE', 'ADD'} and all(c['impacts'] for c in by_id.values())

    hold = copy.deepcopy(r)
    choose(hold, next(x for x in hold['events'] if x['id'] == e['id']), 'HOLD')
    assert hold['holdings'] == {**r['holdings']}

    reduce = copy.deepcopy(r)
    cash_before = liquid(reduce)
    choose(reduce, next(x for x in reduce['events'] if x['id'] == e['id']), 'REDUCE')
    assert reduce['holdings'] == {'TECH': 200, 'STABLE': 150}
    assert liquid(reduce) > cash_before

    add = copy.deepcopy(r)
    budget = liquid(add) // 10
    cash_before = liquid(add)
    choose(add, next(x for x in add['events'] if x['id'] == e['id']), 'ADD')
    spent = cash_before - liquid(add)
    assert 0 < spent <= budget and spent == by_id['ADD']['estimated_cash_cost_minor']
    assert all(add['holdings'][s] >= q for s, q in holdings.items())


def test_add_is_disabled_without_cash():
    r, e = fire('CH01', cash=0, holdings={'TECH': 100}, salary=0)
    add = next(c for c in e['choices'] if c['id'] == 'ADD')
    assert add['enabled'] is False and add['disabled_reason']
    with pytest.raises(ValueError, match='CHOICE_UNAVAILABLE'):
        engine.decide(r, e['id'], 'ADD')


def test_dividend_follows_holdings():
    r, e = fire('CH18', holdings={})
    assert [c['id'] for c in e['choices']] == ['ACK']

    holdings = {'STABLE': 500}
    r, e = fire('CH18', cash=10_000_000, holdings=holdings)
    dividend = event_choices.holdings_value(r) * 300 // 10000
    cash = copy.deepcopy(r)
    before = liquid(cash)
    choose(cash, next(x for x in cash['events'] if x['id'] == e['id']), 'CASH')
    assert liquid(cash) - before == dividend
    assert any(x['category'] == 'DIVIDEND' and x['amount_minor'] == dividend for x in cash['ledger'])

    reinvest = copy.deepcopy(r)
    choose(reinvest, next(x for x in reinvest['events'] if x['id'] == e['id']), 'REINVEST')
    assert reinvest['holdings']['STABLE'] > 500


@pytest.mark.parametrize('card_id', ['CH03', 'CH04', 'CH06'])
def test_unsupported_assets_are_news(card_id):
    r, e = fire(card_id)
    assert [c['id'] for c in e['choices']] == ['ACK']
    assert e['choices'][0]['description'] == content.EVENT_BY_ID[card_id]['lesson']
    before = (liquid(r), r['quality'], r['salary_minor'])
    choose(r, e, 'ACK')
    assert (liquid(r), r['quality'], r['salary_minor']) == before


def test_legacy_choices_on_saved_events_still_resolve():
    r, e = fire('FA21', cash=100_000_000)
    # A save written before this change carries the old multiplier choices.
    e['choices'] = [
        {'id': 'BALANCED', 'label': '謹慎處理', 'effect_multiplier_bps': 10000, 'estimated_cash_cost_minor': 0}
    ]
    before = liquid(r)
    choose(r, e, 'BALANCED')
    assert liquid(r) == before and e['status'] == 'RESOLVED'


def test_choice_wire_shape_includes_impacts():
    _, e = fire('FA22', cash=100_000_000)
    shaped = wire.shape('Choice', e['choices'][0])
    assert shaped['impacts'] and shaped['estimated_cash_cost_minor'] > 0
    legacy = wire.shape('Choice', {'id': 'X', 'label': 'x', 'effect_multiplier_bps': 10000})
    assert legacy['impacts'] == []
