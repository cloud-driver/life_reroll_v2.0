"""Choices for events whose consequence is not a plain cash cost (data/event_choices.json).

When such an event fires, `prepare` prices each choice from the run at that moment and
stores a concrete `effect` on it, so the preview and the result can never disagree and a
later market move cannot change a decision already shown to the player. `apply` books it.
Amounts are integer TWD cents.
"""

from __future__ import annotations

from . import engine, finance
from .content import STOCK_BY_ID

ASSET_CAP_BPS = 5500  # A single event never costs more than 55% of the player's total assets.
ADD_BUDGET_BPS = 1000  # "加碼" spends at most a tenth of cash and savings.


def total_assets(r):
    m = engine.money(r)
    return max(0, m['cash_minor'] + m['savings_minor'] + m['stocks_minor'] + m['term_minor'])


def liquid(r):
    return r['balances']['cash_minor'] + r['balances']['savings_minor']


def held(r):
    return {sid: qty for sid, qty in r['holdings'].items() if qty}


def holdings_value(r, holdings=None):
    return sum(qty * r['prices'][sid] for sid, qty in (held(r) if holdings is None else holdings).items())


def shock_impact(r, holdings, shock_bps):
    """Expected first-month value change of these holdings from the event's market shock."""
    return sum(
        qty * r['prices'][sid] * shock_bps * STOCK_BY_ID[sid]['beta_bps'] // 1000 // 10000
        for sid, qty in holdings.items()
    )


def buy_plan(r, budget):
    """Spread a cash budget over current holdings by value; fees included."""
    holdings = held(r)
    value = holdings_value(r, holdings)
    plan = {}
    for sid, qty in holdings.items():
        share = budget * qty * r['prices'][sid] // value if value else 0
        n = share * 10000 // (10000 + finance.STOCK_TRADE_FEE_BPS) // r['prices'][sid]
        if n:
            plan[sid] = n
    while plan and sum(n * r['prices'][s] + finance.trade_fee(n * r['prices'][s]) for s, n in plan.items()) > budget:
        sid = max(plan, key=lambda s: plan[s] * r['prices'][s])
        plan[sid] -= 1
        if not plan[sid]:
            del plan[sid]
    return plan


def plan_cost(r, plan):
    return sum(n * r['prices'][s] + finance.trade_fee(n * r['prices'][s]) for s, n in plan.items())


def money_text(minor):
    return f'{abs(minor) // 100:,} 元'


def signed(minor):
    return ('+' if minor >= 0 else '-') + money_text(minor)


def quality_text(delta):
    return f'生活品質 {delta:+d}' if delta else '生活品質不變'


def news(card, impact):
    return [
        {
            'id': 'ACK',
            'label': '了解，繼續',
            'description': card['lesson'],
            'effect_multiplier_bps': 10000,
            'effect': {'cash_delta_minor': 0, 'quality_delta': 0, 'living_delta_minor': 0, 'trades': []},
            'estimated_cash_cost_minor': 0,
            'impacts': [impact],
        }
    ]


def effect(cash=0, quality=0, living=0, trades=()):
    return {'cash_delta_minor': cash, 'quality_delta': quality, 'living_delta_minor': living, 'trades': list(trades)}


def prepare(r, card, event):
    model = card['choice_model']
    if model == 'NEWS':
        event['choices'] = news(card, '這是市場新聞，你沒有持有這類資產，不影響你的資金。')
        return
    choices = [dict(c) for c in card['choices']]
    if model == 'COST':
        cap = total_assets(r) * ASSET_CAP_BPS // 10000
        highest = max(c['cost_minor'] for c in choices)
        # Scale every option by the same factor so the cheaper choices stay cheaper.
        scaled = highest > cap
        for c in choices:
            cost = c['cost_minor'] * cap // highest if scaled else c['cost_minor']
            c['effect'] = effect(cash=-cost, quality=c['quality_delta'])
            c['estimated_cash_cost_minor'] = cost
            c['impacts'] = [f'一次支出 {money_text(cost)}', quality_text(c['quality_delta'])]
            if scaled:
                c['impacts'].append('支出依你目前的總資產等比例調整，最高不超過總資產的 55%')
            if cost > liquid(r):
                c['impacts'].append('可用資金不足，差額會形成未付帳單')
    elif model == 'CAREER_RAISE':
        raise_minor = r['salary_minor'] * card['effect']['salary_change_bps'] // 10000
        for c in choices:
            living = raise_minor * c['living_share_bps'] // 10000
            c['effect'] = effect(quality=c['quality_delta'], living=living)
            c['estimated_cash_cost_minor'] = 0
            c['impacts'] = [
                f'月薪 {signed(raise_minor)}／月（各選項相同）',
                f'每月生活支出 {signed(living)}' if living else '每月生活支出不變',
                f'每月可多存 {money_text(raise_minor - living)}',
                quality_text(c['quality_delta']),
            ]
    elif model == 'MARKET_SHOCK':
        holdings = held(r)
        shock = card['effect']['market_shock_bps']
        if not holdings:
            event['choices'] = news(card, '你目前沒有持股，這次市場變動不影響你的資產。')
            return
        for c in choices:
            after, trades, cost, impacts = dict(holdings), [], 0, []
            if c['action'] == 'REDUCE':
                sells = {sid: qty // 2 for sid, qty in holdings.items() if qty // 2}
                proceeds = sum(n * r['prices'][s] - finance.trade_fee(n * r['prices'][s]) for s, n in sells.items())
                trades = [{'side': 'SELL', 'stock_id': s, 'quantity': n} for s, n in sells.items()]
                after = {s: q - sells.get(s, 0) for s, q in holdings.items()}
                impacts.append(f'賣出持股，扣交易費後入帳約 {money_text(proceeds)}')
            elif c['action'] == 'ADD':
                plan = buy_plan(r, liquid(r) * ADD_BUDGET_BPS // 10000)
                if not plan:
                    c['enabled'] = False
                    c['disabled_reason'] = '可用資金不足以加碼。'
                cost = plan_cost(r, plan)
                trades = [{'side': 'BUY', 'stock_id': s, 'quantity': n} for s, n in plan.items()]
                after = {s: holdings.get(s, 0) + plan.get(s, 0) for s in {*holdings, *plan}}
                impacts.append(f'買進持股，含交易費約 {money_text(cost)}')
            impacts.append(f'接下來一個月持股市值估計 {signed(shock_impact(r, after, shock))}（實際依市場變動）')
            c['effect'] = effect(trades=trades)
            c['estimated_cash_cost_minor'] = cost
            c['impacts'] = impacts
    elif model == 'DIVIDEND':
        value = holdings_value(r)
        dividend = value * card['dividend_bps'] // 10000
        if not dividend:
            event['choices'] = news(card, '你目前沒有持股，這次不會收到股利。')
            return
        for c in choices:
            trades = []
            if c['action'] == 'REINVEST':
                trades = [{'side': 'BUY', 'stock_id': s, 'quantity': n} for s, n in buy_plan(r, dividend).items()]
                spent = plan_cost(r, {t['stock_id']: t['quantity'] for t in trades})
                c['impacts'] = [f'特別股利 {signed(dividend)}', f'買回持股約 {money_text(spent)}（含交易費）']
            else:
                c['impacts'] = [f'特別股利 {signed(dividend)}，存入現金']
            c['effect'] = effect(cash=dividend, trades=trades)
            c['estimated_cash_cost_minor'] = 0
    event['choices'] = choices


def apply(r, choice):
    """Book a prepared choice's non-cash effects; `engine.decide` books its cash first."""
    eff = choice['effect']
    r['quality'] = max(0, min(100, r['quality'] + eff['quality_delta']))
    r['living_minor'] += eff['living_delta_minor']
    for t in eff['trades']:
        sid, qty = t['stock_id'], t['quantity']
        if t['side'] == 'SELL' and r['holdings'].get(sid, 0) >= qty:
            finance.sell_stock(r, sid, qty)
        elif t['side'] == 'BUY' and qty * r['prices'][sid] + finance.trade_fee(qty * r['prices'][sid]) <= liquid(r):
            finance.buy_stock(r, sid, qty)
