"""Counterfactual engine rollouts. Never read the real run seed or future plan.

Both branches use paired independent scenario seeds and the same conservative
event policy. Financial actions and claims use the production calculators.
"""
from . import engine,finance,rebirth

VERSION='scenarios-20261023-2'
HORIZON=60
SAMPLES=24

def compact(r):
    # Past accounting has no effect on future rules. Keep debts/policies/claims
    # and known event ids; bound the copies made by next_step's checkpoints.
    r['ledger']=[];r['snapshots']=[];r['quotes']=[];r['transactions']=[]
    r['networth_history']=r['networth_history'][-1:]
    r['quality_history']=r['quality_history'][-1:]
    r['price_history']={k:v[-1:] for k,v in r['price_history'].items()}
    r['events']=[e for e in r['events'] if e['id']==r.get('pending_event')]

def action(r,kind,params):
    q=finance.quote(r,kind,params)
    if not q['eligible']:return False
    finance.execute(r,q)
    return True

def claims(r,e):
    from .handlers import assess_claim
    for p in engine.coverage_for(r,e):
        if any(c['event_id']==e['id'] and c['policy_id']==p['id'] for c in r['claims']):continue
        claim={'id':engine.uid(),'policy_id':p['id'],'policy_product_id':p['product_id'],'event_id':e['id'],
            'benefit_code':p['product_id'],'status':'SUBMITTED','approved_minor':0,'paid_minor':0,
            'payable_index':None,'reason_codes':[],'explanation':'情境試算','required_evidence_ids':[],
            'ledger_entry_ids':[],'recipient':'PLAYER'}
        r['claims'].append(claim);assess_claim(r,e,claim)

def resolve(r,e,observe=lambda:None):
    """Smallest expense choice, file eligible claims, liquidate, then borrow.

    Return whether extra funds were needed. This is a declared simulation
    policy, never an action on the player's actual save.
    """
    choice=min(e['choices'],key=lambda c:(c['estimated_cash_cost_minor'],-c['effect_multiplier_bps']))
    engine.decide(r,e['id'],choice['id']);observe();claims(r,e);observe()
    gap=False
    for _ in range(20):
        if r['status']!='FUNDING':break
        f=engine.funding(r,e)
        if f['can_pay']:
            engine.spend(r,f['remaining_minor'],'MEDICAL','情境必要治療費',e['id'])
            e['funding']['paid_minor']+=f['remaining_minor'];e['status']='RESOLVED';r['status']='EVENT_RESULT';observe();break
        gap=True
        if f['can_wait']:
            r['month_index']+=1;engine.monthly_market(r);engine.monthly_obligations(r)
            observe()
            if r['status']=='ENDED':break
            continue
        done=False
        for sid,qty in list(r['holdings'].items()):
            if qty and action(r,'STOCK_SELL',{'stock_id':sid,'quantity':qty}):done=True;break
        if done:continue
        t=next((t for t in r['terms'] if t['status']=='ACTIVE'),None)
        if t and action(r,'TERM_CLOSE',{'term_deposit_id':t['id']}):continue
        room=max(0,r['salary_minor']*24-sum(l['principal_minor'] for l in r['loans'] if l['status']!='PAID'))
        need=max(0,f['remaining_minor']-f['available_now_minor'])
        if room and action(r,'LOAN_BORROW',{'amount_minor':min(room,need),'term_months':60}):continue
        if not f['can_confirm_failure']:raise ValueError('SCENARIO_FUNDING_STALLED')
        e['status']='RESOLVED';engine.end(r,'UNFUNDED_CRITICAL_CARE');break
    if r['status']=='FUNDING':raise ValueError('SCENARIO_FUNDING_STALLED')
    return gap

def rollout(r,months=HORIZON,strategy='CURRENT',cancel=lambda:False):
    """Consumes a disposable run, returns aggregates only; no persistence/Qwen."""
    opening=engine.money(r)['net_worth_minor'];start=r['month_index'];target=start+months
    if strategy=='BASIC' and r['lifestyle']!='BASIC':
        r['living_minor']=max(2000000,r['persona']['annual_income_minor']//28)*75//100
        r['quality']=max(0,min(100,r['quality']-4-{'BALANCED':0,'COMFORT':5}.get(r['lifestyle'],-4)))
        r['lifestyle']='BASIC'
    elif strategy not in ('BASIC','CURRENT'):raise ValueError('INVALID_STRATEGY')
    r['status']='EXPLORING';r['scene_id']='HOME';r['daily_phase']='HOME_READY'
    min_liquid=r['balances']['cash_minor']+r['balances']['savings_minor'];shortage=False;qualities=[]
    # Include pre-existing overdue obligations; do not silently forgive them.
    def observe():
        nonlocal min_liquid,shortage
        min_liquid=min(min_liquid,r['balances']['cash_minor']+r['balances']['savings_minor'])
        shortage|=any(b['status']!='PAID' and b['remaining_minor']>0 for b in r['bills']) or any(l['status']=='DELINQUENT' for l in r['loans'])
    observe()
    compact(r)
    while r['month_index']<target and r['status']!='ENDED':
        if cancel():return None
        month_target=min(target,r['month_index']+1)
        r['advance']={'id':engine.uid(),'from_date':engine.sim_date(r),'status':'PROCESSING','roll_value':5,
            'target_date':engine.sim_date({'month_index':target}),'remaining_months':target-r['month_index'],
            'blocking_event_id':None,'ledger_start':0,'event_start':0,'opening_state':engine.snapshot(r)}
        r['target_index']=month_target;r['status']='ADVANCING';engine.next_step(r);observe()
        for _ in range(100):
            if r['status']=='EVENT_PENDING':
                e=engine.event_by_id(r,r['pending_event']);shortage|=resolve(r,e,observe);observe()
            elif r['status']=='EVENT_RESULT':engine.acknowledge(r,r['pending_event']);observe()
            else:break
        if r['status'] not in ('TURN_REVIEW','ENDED'):raise ValueError('SCENARIO_STALLED')
        qualities.append(r['quality']);compact(r)
    return {'shortage':bool(shortage),'ended_early':r['status']=='ENDED',
        'months':r['month_index']-start,'net_change_minor':engine.money(r)['net_worth_minor']-opening,
        'minimum_liquidity_minor':min_liquid,'quality':round(sum(qualities)/max(1,len(qualities)))}

def hypothetical(r,seed):
    # snapshot() is an explicit allowlist: no real seed, planned future, story,
    # quotes or transactions cross this boundary.
    return engine.create_run(r['persona'],seed,r['start_age'],engine.snapshot(r))

def summarize(values):
    def span(key):
        a=sorted(v[key] for v in values);return {'low':a[len(a)//10],'median':a[len(a)//2],'high':a[min(len(a)-1,len(a)*9//10)]}
    return {'samples':len(values),'shortage_count':sum(v['shortage'] for v in values),
        'ended_early_count':sum(v['ended_early'] for v in values),'net_change_minor':span('net_change_minor'),
        'minimum_liquidity_minor':span('minimum_liquidity_minor'),'quality':span('quality'),
        'duration_months':{'min':min(v['months'] for v in values),'max':max(v['months'] for v in values)}}

def compare(persona,current,point,seeds,cancel=lambda:False):
    # Rollouts discard historical accounting before the first simulated month.
    # Trim that same read-only history before restore() deep-copies it 48 times.
    # Keep every past event for plan exclusions and all policies/debts/claims.
    def lean(state):
        return {**state,'ledger':[],
                'price_history':{k:v[-1:] for k,v in state['price_history'].items()},
                'networth_history':state['networth_history'][-1:],
                'quality_history':state['quality_history'][-1:]}
    current={**current,'initial':lean(current['initial']),
             'snapshots':[{**s,'state':lean(s['state'])} for s in current['snapshots'] if s['point_id']==point['id']]}
    variants={}
    for strategy in ('CURRENT','BASIC'):
        values=[]
        for seed in seeds:
            if cancel():return None
            r=rebirth.restore(persona,current,point['id'],seed)
            value=rollout(r,strategy=strategy,cancel=cancel)
            if value is None:return None
            values.append(value)
        variants[strategy]=summarize(values)
    return {'point_id':point['id'],'variants':variants}
