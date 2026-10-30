"""Deterministic, auditable life simulation. Every amount is integer TWD cents."""
from __future__ import annotations
import copy
import hashlib
import random
from datetime import datetime, timedelta
from uuid import uuid4
from .content import PERSONAS,EVENTS,EVENT_BY_ID,STOCKS,STOCK_BY_ID,PRODUCTS,PRODUCT_BY_ID,CONTENT_VERSION

def uid():return uuid4().hex
def now():return datetime.now().astimezone().isoformat(timespec='seconds')
def sim_date(r):
    i=r['month_index'];return f'{2026+i//12:04d}-{i%12+1:02d}-01'
def age(r):return r['start_age']+r['month_index']//12
def money(r):
    b=r['balances'];stocks=sum(r['holdings'].get(s['id'],0)*r['prices'][s['id']] for s in STOCKS)
    return {**b,'stocks_minor':stocks,'term_minor':sum(t['principal_minor']+t['interest_minor'] for t in r['terms'] if t['status']=='ACTIVE'),
            'term_principal_minor':sum(t['principal_minor'] for t in r['terms'] if t['status']=='ACTIVE'),
            'receivables_minor':sum(max(0,c['approved_minor']-c['paid_minor']) for c in r['claims'] if c['status']=='APPROVED'),
            'loan_minor':sum(l['principal_minor']+l['interest_minor'] for l in r['loans'] if l['status']!='PAID'),
            'bill_minor':sum(x['remaining_minor'] for x in r['bills'] if x['status']!='PAID' and not x.get('related_loan_id')),
            'net_worth_minor':b['cash_minor']+b['savings_minor']+stocks+
                sum(t['principal_minor']+t['interest_minor'] for t in r['terms'] if t['status']=='ACTIVE')-
                sum(l['principal_minor']+l['interest_minor'] for l in r['loans'] if l['status']!='PAID')-
                sum(x['remaining_minor'] for x in r['bills'] if x['status']!='PAID' and not x.get('related_loan_id'))}
def ledger(r,category,amount,account='CASH',cashflow='NONE',description='',event_id=None,transaction_id=None):
    if amount==0:return
    category={'EVENT':'OTHER','FEE':'OTHER','BILL_PAYMENT':'TRANSFER'}.get(category,category)
    r['ledger'].append({'id':uid(),'sim_date':sim_date(r),'category':category,'amount_minor':int(amount),
        'account':account,'cashflow_class':cashflow,'description':description or category,
        'event_id':event_id,'transaction_id':transaction_id})
def income(r,amount,category='OTHER',description='',event_id=None):
    r['balances']['cash_minor']+=int(amount)
    ledger(r,category,amount,cashflow='INCOME',description=description,event_id=event_id)
def spend(r,amount,category='OTHER',description='',event_id=None,force_bill=False,cashflow='EXPENSE'):
    amount=max(0,int(amount));left=amount
    for k in ('cash_minor','savings_minor'):
        used=min(r['balances'][k],left);r['balances'][k]-=used;left-=used
        if used:ledger(r,category,-used,'CASH' if k=='cash_minor' else 'SAVINGS',cashflow,description,event_id)
    if left and force_bill:
        r['bills'].append({'id':uid(),'category':category,'due_on':sim_date(r),'total_minor':left,'remaining_minor':left,
                           'status':'OVERDUE','related_loan_id':None,'related_policy_id':None,'event_id':event_id,'explanation':'可用現金不足，形成未付義務'})
        ledger(r,category,-left,'BILL','EXPENSE',description+'（尚未支付）',event_id)
    return left
def checkpoint(r):
    point={'date':sim_date(r),'net_worth_minor':money(r)['net_worth_minor']}
    if r['networth_history'] and r['networth_history'][-1]['date']==point['date']:
        r['networth_history'][-1]=point
    else:r['networth_history'].append(point)
def change(r):
    r['version']+=1;r['saved_at']=now();checkpoint(r)
    return public_run(r)
def public_run(r):
    d={k:copy.deepcopy(v) for k,v in r.items() if k not in {'seed','planned','snapshots','quotes','transactions','ledger','history','initial','market_residual','seen_cards','story_text'}}
    d['age']=age(r);d['current_date']=sim_date(r);d['balances']=money(r)
    d['pending_event_id']=r['pending_event']
    d['daily_phase']=r.get('daily_phase','HOME_READY' if r['scene_id'] in ('HOME','STREET') else 'FREE_TIME')
    d['allowed_actions']=allowed(r)
    return d
def allowed(r):
    s=r['status']
    if s=='EXPLORING':
        phase=r.get('daily_phase','HOME_READY')
        return ['SCENE_TRANSITION','SAVE','SUBMIT_CLAIM']+(['QUOTE'] if phase in ('HOME_READY','FREE_TIME') else [])+(['CHANGE_LIFESTYLE','ROLL'] if r['scene_id']=='HOME' and phase=='HOME_READY' else [])
    return ({'INITIAL_ALLOCATION':['SCENE_TRANSITION','COMPLETE_INITIAL_ALLOCATION','QUOTE','SAVE'],
             'EXPLORING':['SCENE_TRANSITION','CHANGE_LIFESTYLE','SAVE','QUOTE','SUBMIT_CLAIM']+(['ROLL'] if r['scene_id']=='HOME' else []),
             'EVENT_PENDING':['CHOOSE_EVENT','SUBMIT_CLAIM','SAVE'],
             'FUNDING':['PAY_FUNDING','WAIT_FUNDING','CONFIRM_FAILURE','SUBMIT_CLAIM','QUOTE','SAVE'],
             'EVENT_RESULT':['ACK_EVENT','SUBMIT_CLAIM','SAVE'],'TURN_REVIEW':['ACK_TURN','SAVE'],
             'ENDED':['READ_REPORT','SAVE']}).get(s,['SAVE'])
def match(cond,p,at_age):
    if not cond:return True
    if 'unsupported_source_rule' in cond:return False
    v=at_age if cond['field']=='age' else p.get(cond['field'])
    t=cond['value'];op=cond['op']
    return {'==':lambda:v==t,'!=':lambda:v!=t,'>=':lambda:v>=t,'<=':lambda:v<=t,'in':lambda:v in t}[op]()
def plan(seed,persona,start_age,exclude=(),min_index=0,anchor=None):
    rng=random.Random(seed);available=[e for e in EVENTS if e['id'] not in exclude]
    planned=[];at=start_age+2
    while at <= 95:
        subset=[e for e in available if match(e['condition'],persona,at) and
                (e['kind']!='CAREER' or at<=60) and
                (e['id'] not in ('FA12','FA13') or at<=55) and
                (e['id']!='FA27' or at>=60)]
        if subset:
            category='HEALTH' if len(planned)%6==4 else 'TRAVEL' if len(planned)%5==1 else 'CAREER' if len(planned)%7==0 else None
            candidates=[e for e in subset if e['kind']==category] or subset
            selected=rng.choice(candidates)
            idx=(at-start_age)*12+rng.randrange(2,11)
            if idx >= min_index:planned.append({'at_index':idx,'card_id':selected['id'],'anchor':False})
            available.remove(selected)
        at+=rng.randrange(4,7)
    required=[('CH07',start_age+8),('CR03',start_age+16),
              ('CH08' if persona['industry']!='軍公教' else 'CR04',start_age+24)]
    for required_id,target_age in required:
        if required_id in exclude:continue
        idx=(target_age-start_age)*12+5
        if idx<min_index or target_age>60:continue
        planned=[x for x in planned if x['card_id']!=required_id]
        while any(x['at_index']==idx for x in planned):idx+=1
        planned.append({'at_index':idx,'card_id':required_id,'anchor':False})
    if anchor:
        planned=[x for x in planned if x['at_index']!=anchor['at_index'] and x['card_id']!=anchor['card_id']]
        planned.append({**anchor,'anchor':True})
    return sorted(planned,key=lambda x:x['at_index'])
def create_run(persona,seed,start_age=None,inherit=None,anchor=None):
    rng=random.Random(seed);start_age=start_age or rng.randint(25,30)
    p=copy.deepcopy(persona);p['annual_income']=p['annual_income_minor']//100
    initial=max(16000000,min(100000000,int(p['annual_income_minor']*(0.33+rng.random()*0.33))))
    r={'id':uid(),'run_index':1,'status':'INITIAL_ALLOCATION','version':1,'scene_id':'HOME','daily_phase':'HOME_READY','persona':p,
       'start_age':start_age,'month_index':0,'target_index':None,'advance':None,'pending_event':None,
       'employment_status':'EMPLOYED','current_occupation':p['occupation'],'unemployment_until_index':None,
       'prior_salary_minor':p['annual_income_minor']//12,
       'balances':{'cash_minor':initial,'savings_minor':0},'salary_minor':p['annual_income_minor']//12,
       'living_minor':max(2000000,p['annual_income_minor']//28),'support_minor':0,
       'lifestyle':'BALANCED','quality':55,'negative_years':0,'prices':{s['id']:10000 for s in STOCKS},
       'price_history':{s['id']:[{'date':'2026-01-01','price_minor':10000}] for s in STOCKS},
       'holdings':{},'holding_cost_minor':{},'terms':[],'loans':[],'policies':[],'claims':[],'events':[],
       'ledger':[],'bills':[],'quotes':[],'transactions':[],'snapshots':[],'networth_history':[],
       'seed':seed,'planned':plan(seed,p,start_age),'story_text':{},'market_residual':0,'saved_at':now(),'end_reason':None,
       'seen_cards':[],'quality_history':[]}
    r['initial']=snapshot(r)
    checkpoint(r)
    if inherit:
        for k in ('month_index','balances','salary_minor','living_minor','support_minor','lifestyle','quality',
                  'employment_status','current_occupation','unemployment_until_index','prior_salary_minor',
                  'negative_years','prices','price_history','holdings','holding_cost_minor','terms','loans','policies','claims',
                  'ledger','bills','events','quality_history','networth_history'):
            r[k]=copy.deepcopy(inherit[k])
        r['status']='EXPLORING';r['scene_id']='HOME';r['initial']=copy.deepcopy(inherit)
        r['planned']=plan(seed,p,start_age,exclude=[x['card_id'] for x in r['events'] if x['status']!='PENDING'],
                          min_index=r['month_index'],anchor=anchor)
    return r
def snapshot(r):
    return {k:copy.deepcopy(v) for k,v in r.items() if k in ('month_index','balances','salary_minor','living_minor','support_minor',
        'employment_status','current_occupation','unemployment_until_index','prior_salary_minor',
        'lifestyle','quality','negative_years','prices','price_history','holdings','holding_cost_minor','terms','loans','policies',
        'claims','ledger','bills','events','quality_history','networth_history')}
def monthly_market(r):
    idx=r['month_index'];rnd=random.Random(f'{r["seed"]}:market:{idx}')
    # Shared two-year cycles and occasional broad sell-offs make diversification
    # imperfect. Derive cycles from seed/date so reloads and rewinds need no new
    # mutable market state and never reprice an already-recorded month.
    cycle=random.Random(f'{r["seed"]}:cycle:{idx//24}').random()
    regime=75 if cycle<.30 else -110 if cycle<.55 else 10
    market=max(-1100,min(1100,int(rnd.gauss(20,310))))+regime
    if rnd.random()<.015:market-=rnd.randint(900,1800)
    market+=r.pop('market_residual',0)
    for s in STOCKS:
        independent=random.Random(f'{r["seed"]}:{s["id"]}:{idx}').gauss(0,s['vol_bps']/3.46)
        change_bps=max(-2500,min(1800,int(market*s['beta_bps']/1000+s['drift_bps']/12+independent)))
        old=r['prices'][s['id']];new=max(100,int(old*(10000+change_bps)/10000))
        r['prices'][s['id']]=new;r['price_history'][s['id']].append({'date':sim_date(r),'price_minor':new})
        if idx%12==0:
            qty=r['holdings'].get(s['id'],0)
            if qty:income(r,qty*new*s['dividend_bps']//10000,'DIVIDEND',f'{s["name"]}模擬股利')
def monthly_obligations(r):
    if r['unemployment_until_index'] is not None and r['month_index']>=r['unemployment_until_index']:
        r['salary_minor']=r.get('prior_salary_minor',r['persona']['annual_income_minor']//12)*85//100
        r['employment_status']='EMPLOYED';r['current_occupation']='重新就業';r['unemployment_until_index']=None
    if age(r)>=65 and r['employment_status']!='RETIRED':
        r['employment_status']='RETIRED';r['salary_minor']=0;r['unemployment_until_index']=None
    savings_interest=r['balances']['savings_minor']*80//120000
    if savings_interest:
        r['balances']['savings_minor']+=savings_interest
        ledger(r,'INTEREST',savings_interest,'SAVINGS','INCOME','活存月息')
    base=r['salary_minor']
    if base>0:income(r,base,'SALARY','當月薪資')
    spend(r,r['living_minor'],'LIVING','必要生活費',force_bill=True)
    if r['support_minor']:spend(r,r['support_minor'],'SUPPORT','家庭扶養費',force_bill=True)
    for t in r['terms']:
        if t['status']!='ACTIVE':continue
        t['interest_minor']+=t['principal_minor']*t['rate_bps']//120000
        if r['month_index']>=t['matures_index']:
            t['status']='MATURED'
            r['balances']['cash_minor']+=t['principal_minor']
            ledger(r,'PRINCIPAL',t['principal_minor'],cashflow='INTERNAL',description='定存本金返還')
            income(r,t['interest_minor'],'INTEREST','定存利息入帳')
            if t.get('auto_renew'):
                principal=t['principal_minor']+t['interest_minor'];spend(r,principal,'TRANSFER','自動續存',cashflow='INTERNAL')
                t.update(status='ACTIVE',principal_minor=principal,interest_minor=0,matures_index=r['month_index']+t['term_months'])
    for l in r['loans']:
        if l['status']=='PAID':continue
        interest=l['principal_minor']*l['rate_bps']//120000
        l['interest_minor']+=interest
        due=min(l['principal_minor'],l['original_minor']//max(1,l['term_months']))+l['interest_minor']
        if r['balances']['cash_minor']+r['balances']['savings_minor']>=due:
            spend(r,l['interest_minor'],'INTEREST','貸款利息')
            spend(r,due-l['interest_minor'],'PRINCIPAL','貸款本金',cashflow='INTERNAL')
            l['principal_minor']-=due-l['interest_minor'];l['interest_minor']=0
            l['status']='PAID' if l['principal_minor']==0 else 'ACTIVE'
        else:l['status']='DELINQUENT'
    for p in r['policies']:
        if p['status'] in ('SURRENDERED','EXPIRED'):continue
        if r['month_index']<p['coverage_from_index']:continue
        if p['status']=='WAITING' and r['month_index']>=p['coverage_from_index']+PRODUCT_BY_ID[p['product_id']]['waiting_months']:
            p['status']='ACTIVE'
        if p['status'] in ('ACTIVE','WAITING') and r['month_index']>=p['next_premium_index']:
            if p['auto_pay'] and r['balances']['cash_minor']+r['balances']['savings_minor']>=p['premium_minor']:
                spend(r,p['premium_minor'],'PREMIUM','模擬保費');p['next_premium_index']+=12;p['status']='ACTIVE'
            else:
                p['status']='GRACE';p['grace_until_index']=r['month_index']+2
                r['bills'].append({'id':uid(),'category':'PREMIUM','total_minor':p['premium_minor'],
                        'remaining_minor':p['premium_minor'],'due_on':sim_date(r),'status':'OPEN',
                        'related_policy_id':p['id'],'related_loan_id':None,'explanation':'保費未繳，寬限後失效'})
        if p['status']=='GRACE' and r['month_index']>p.get('grace_until_index',10**9):p['status']='LAPSED'
    for c in r['claims']:
        if c['status']=='APPROVED' and r['month_index']>=c['payable_index']:
            income(r,c['approved_minor'],'CLAIM','理賠款入帳',c['event_id']);c['paid_minor']=c['approved_minor'];c['status']='PAID'
    if r['month_index']%12==0:
        r['negative_years']=r['negative_years']+1 if money(r)['net_worth_minor']<0 else 0
        r['quality_history'].append({'age':age(r),'quality':r['quality'],'net_worth_minor':money(r)['net_worth_minor']})
        if r['negative_years']>=7:end(r,'NEGATIVE_NET_WORTH_7Y')
def next_step(r):
    while r['status']=='ADVANCING':
        due=next((item for item in r['planned'] if item['at_index']<=r['month_index'] and
                  item['card_id'] not in r['seen_cards']),None)
        if due:
            # Funding waits have already settled these months. Queue their events
            # without charging the same month twice or silently skipping a card.
            pre_event_state=copy.deepcopy((r.get('advance') or {}).get('opening_state') or r['initial'])
        else:
            if r['month_index']>=r['target_index']:break
            # The schedule is fixed before stepping the month. Only event months
            # need a restore point; copying decades of ledgers every month is
            # quadratic in the length of a life.
            upcoming=any(item['at_index']<=r['month_index']+1 and
                         item['card_id'] not in r['seen_cards'] for item in r['planned'])
            pre_event_state=snapshot(r) if upcoming else None
            r['month_index']+=1
            monthly_market(r);monthly_obligations(r)
            checkpoint(r)
            if r['status']=='ENDED':return
            due=next((item for item in r['planned'] if item['at_index']<=r['month_index'] and
                      item['card_id'] not in r['seen_cards']),None)
        if due:
            card=EVENT_BY_ID[due['card_id']]
            r['snapshots'].append({'point_id':uid(),'at_index':due['at_index'],'anchor':copy.deepcopy(due),
                                   'title':card['title'],'state':pre_event_state})
            r['seen_cards'].append(card['id'])
            event={'id':uid(),'card_id':card['id'],'kind':card['kind'],'title':card['title'],
                   'narrative':r.get('story_text',{}).get(card['id']) or card['description'],
                   'occurred_on':f'{2026+due["at_index"]//12:04d}-{due["at_index"]%12+1:02d}-01','at_index':due['at_index'],
                   'status':'PENDING','is_rebirth_anchor':bool(due['anchor']),
                   'choices':copy.deepcopy(card['choices']),'evidence':[], 'outcome':None}
            event['eligible_policy_ids']=[p['id'] for p in coverage_for(r,event)]
            event['visual_key']=card['id']
            event['balance_before_minor']=r['balances']['cash_minor']+r['balances']['savings_minor']
            if card['kind'] in ('HEALTH','ACCIDENT'):
                r['event_return_scene']=r['scene_id'];r['scene_id']='HOSPITAL'
            for choice in event['choices']:
                cost=max(0,-card['effect']['cash_delta_minor']*choice['effect_multiplier_bps']//10000)
                choice['estimated_cash_cost_minor']=cost
                if cost>r['balances']['cash_minor']+r['balances']['savings_minor']:
                    choice['description']='需要額外籌資；一般生活支出不足時會形成未付帳單。'
            r['events'].append(event);r['pending_event']=event['id'];r['status']='EVENT_PENDING'
            r['advance']['status']='PAUSED_EVENT';r['advance']['blocking_event_id']=event['id'];return
    if r['status']=='ADVANCING':
        r['status']='TURN_REVIEW';r['advance']['status']='AWAITING_REVIEW'
        r['advance']['current_date']=sim_date(r);r['advance']['remaining_months']=0
        finalize_advance(r)

def asset_snapshot(r):
    b=money(r)
    return {'as_of':sim_date(r),'balances':b,
        'term_interest_minor':sum(t['interest_minor'] for t in r['terms'] if t['status']=='ACTIVE'),
        'holdings':[{'stock_id':sid,'quantity':qty,'cost_basis_minor':r['holding_cost_minor'].get(sid,0),
          'market_value_minor':qty*r['prices'][sid]} for sid,qty in r['holdings'].items() if qty],
        'active_policy_count':sum(p['status'] in ('ACTIVE','WAITING','GRACE') for p in r['policies']),
        'lapsed_policy_count':sum(p['status']=='LAPSED' for p in r['policies']),
        'annual_premium_minor':sum(p['premium_minor'] for p in r['policies'] if p['status'] in ('ACTIVE','WAITING','GRACE'))}

def finalize_advance(r):
    a=r.get('advance')
    if not a or 'from_date' not in a:return
    a['current_date']=sim_date(r);a['remaining_months']=max(0,(r.get('target_index') or r['month_index'])-r['month_index'])
    a['closing_snapshot']=asset_snapshot(r)
    entries=r['ledger'][a.get('ledger_start',0):]
    opening=a.get('opening_snapshot',{}).get('balances',{}).get('net_worth_minor',money(r)['net_worth_minor'])
    a['summary']={'from_date':a['from_date'],'to_date':sim_date(r),
       'income_minor':sum(x['amount_minor'] for x in entries if x['cashflow_class']=='INCOME'),
       'expense_minor':-sum(x['amount_minor'] for x in entries if x['cashflow_class']=='EXPENSE'),
       'premium_minor':-sum(x['amount_minor'] for x in entries if x['category']=='PREMIUM' and x['cashflow_class']=='EXPENSE'),
       'claims_paid_minor':sum(x['amount_minor'] for x in entries if x['category']=='CLAIM'),
       'net_worth_change_minor':money(r)['net_worth_minor']-opening,
       'event_ids':[e['id'] for e in r['events'][a.get('event_start',0):]]}
def end(r,reason):
    r['status']='ENDED';r['end_reason']=reason;r['pending_event']=None
    if r['advance']:r['advance']['status']='TERMINATED' if reason!='AGE_COMPLETED' else 'COMPLETED'
    finalize_advance(r)
    for p in r['policies'] if reason=='UNFUNDED_CRITICAL_CARE' else []:
        if (p['product_id']=='LIFE' and p['status'] in ('ACTIVE','WAITING','GRACE') and
                r['month_index']>=p['coverage_from_index']+PRODUCT_BY_ID['LIFE']['waiting_months']):
            r.setdefault('estate_benefits_approved_minor',0)
            r['estate_benefits_approved_minor']+=p['coverage_minor']
def event_by_id(r,id_):return next((x for x in r['events'] if x['id']==id_),None)
def coverage_for(r,e):
    card=EVENT_BY_ID[e['card_id']]
    eligible=[]
    for p in r['policies']:
        cfg=PRODUCT_BY_ID[p['product_id']]
        if 'eligible_policy_ids' in e:
            if p['id'] in e['eligible_policy_ids']:eligible.append(p)
            continue
        if p['status'] not in ('ACTIVE','GRACE') or e['at_index']<p['coverage_from_index']+cfg['waiting_months']:continue
        if p['product_id']=='LIFE':continue
        if p['product_id']==card.get('insurance_category') or (p['product_id']=='CRITICAL_ILLNESS' and card['critical'] and card['kind']=='HEALTH'):
            eligible.append(p)
    return eligible
def funding(r,e):
    f=e.get('funding') or {}
    outstanding=max(0,f.get('required_minor',0)-f.get('paid_minor',0))
    liquid=r['balances']['cash_minor']+r['balances']['savings_minor']
    holdings=sum(r['holdings'].get(s['id'],0)*r['prices'][s['id']]*985//1000 for s in STOCKS)
    deposits=sum(t['principal_minor']+t['interest_minor']*7//10 for t in r['terms'] if t['status']=='ACTIVE')
    borrowed=sum(l['principal_minor'] for l in r['loans'] if l['status']!='PAID')
    loan_room=max(0,r['salary_minor']*12*2-borrowed)
    future=sum(c['approved_minor']-c['paid_minor'] for c in r['claims'] if c['event_id']==e['id'] and c['status']=='APPROVED' and c['payable_index']<=e['at_index']+3)
    claim_not_filed=[p for p in coverage_for(r,e) if not any(c['event_id']==e['id'] and c['policy_id']==p['id'] for c in r['claims'])]
    claim_needs_info=any(c['event_id']==e['id'] and c['status']=='NEEDS_INFO' for c in r['claims'])
    options=[{'kind':'TRANSFER','available_minor':r['balances']['savings_minor'],'enabled':r['balances']['savings_minor']>0},
             {'kind':'STOCK_SELL','available_minor':holdings,'enabled':holdings>0},
             {'kind':'TERM_CLOSE','available_minor':deposits,'enabled':deposits>0},
             {'kind':'LOAN_BORROW','available_minor':loan_room,'enabled':loan_room>0},
             {'kind':'CLAIM','available_minor':future,'enabled':bool(claim_not_filed) or claim_needs_info or future>0}]
    deadline=e['at_index']+3
    next_due=min([c['payable_index'] for c in r['claims'] if c['event_id']==e['id'] and c['status']=='APPROVED']+[deadline])
    can_wait=next_due>r['month_index'] and r['month_index']<deadline and future>0
    return {'event_id':e['id'],'required_minor':f.get('required_minor',0),'paid_minor':f.get('paid_minor',0),
            'remaining_minor':outstanding,'available_now_minor':liquid,'deadline':f'{2026+deadline//12}-{deadline%12+1:02d}-01',
            'can_pay':liquid>=outstanding,'can_wait':can_wait,'next_wait_until':f'{2026+next_due//12}-{next_due%12+1:02d}-01' if can_wait else None,
            'can_confirm_failure':liquid+holdings+deposits+loan_room<outstanding and not
                  (holdings or deposits or loan_room or claim_not_filed or claim_needs_info or can_wait or future),
            'options':options}
def decide(r,event_id,choice_id):
    e=event_by_id(r,event_id)
    if r['status']!='EVENT_PENDING' or not e or r['pending_event']!=e['id']:raise ValueError('STATE_CONFLICT')
    card=EVENT_BY_ID[e['card_id']]
    choice=next((c for c in e['choices'] if c['id']==choice_id),None)
    if not choice:raise ValueError('CHOICE_UNAVAILABLE')
    mul=choice['effect_multiplier_bps'];eff=card['effect']
    delta=eff['cash_delta_minor']*mul//10000
    e['choice_id']=choice_id;e['evidence']=[{'id':uid(),'event_id':e['id'],'label':'遊戲事件紀錄','available_on':sim_date(r)}]
    r['quality']=max(0,min(100,r['quality']+eff['quality_delta']*mul//10000))
    r['salary_minor']=max(0,r['salary_minor']*(10000+eff['salary_change_bps']*mul//10000)//10000)
    if card['id'] in ('CH08','CR04') and r['employment_status']=='EMPLOYED':
        r['prior_salary_minor']=r['salary_minor'];r['salary_minor']=0
        r['employment_status']='UNEMPLOYED';r['unemployment_until_index']=r['month_index']+6
    if card['id']=='CR03' and r['employment_status']=='EMPLOYED':
        r['salary_minor']=r['salary_minor']*110//100
        r['current_occupation']='轉職後的'+r['persona']['occupation']
    if card['id']=='FA12':r['support_minor']+=1000000*mul//10000
    if card['id']=='FA04':r['support_minor']+=2500000*mul//10000
    r['living_minor']+=max(0,eff['monthly_cost_delta_minor']*mul//10000)
    r['market_residual']=eff['market_shock_bps']*mul//10000
    if card['critical'] and delta<0:
        e['funding']={'required_minor':-delta,'paid_minor':0}
        r['status']='FUNDING';e['status']='FUNDING'
    else:
        if delta>=0:income(r,delta,'EVENT',card['title'],e['id'])
        else:spend(r,-delta,'EVENT',card['title'],e['id'],force_bill=True)
        e['status']='RESOLVED';r['status']='EVENT_RESULT'
    e['outcome']={'choice_id':choice_id,'cash_delta_minor':delta,'quality_delta':eff['quality_delta']*mul//10000,
                  'is_terminal':False,'summary':f'選擇「{choice["label"]}」，費用與效果已記錄。'}
    e['balance_after_minor']=r['balances']['cash_minor']+r['balances']['savings_minor']
    return e
def acknowledge(r,event_id):
    e=event_by_id(r,event_id)
    if not e or r['pending_event']!=event_id or r['status']!='EVENT_RESULT':raise ValueError('STATE_CONFLICT')
    e['status']='ACKNOWLEDGED';r['pending_event']=None;r['status']='ADVANCING';r['advance']['status']='PROCESSING'
    r['scene_id']=r.pop('event_return_scene',r['scene_id'])
    next_step(r)
def report(r):
    if r['status']!='ENDED':raise ValueError('REPORT_NOT_READY')
    cats={}
    for x in r['ledger']:
        if x['cashflow_class'] not in ('INCOME','EXPENSE'):continue
        key=x['category'];cats.setdefault(key,{'code':key,'label':key,'amount_minor':0,'entry_ids':[]})
        cats[key]['amount_minor']+=x['amount_minor'];cats[key]['entry_ids'].append(x['id'])
    effects=[]
    for e in r['events']:
        claims=[c for c in r['claims'] if c['event_id']==e['id']]
        if claims:
            paid=sum(c['paid_minor'] for c in claims)
            effects.append({'event_id':e['id'],'gross_cost_minor':max(0,-(e['outcome'] or {}).get('cash_delta_minor',0)),
                            'reimbursement_paid_minor':sum(c['paid_minor'] for c in claims if PRODUCT_BY_ID[c['policy_product_id']]['benefit_type']=='REIMBURSEMENT'),
                            'fixed_benefits_paid_minor':sum(c['paid_minor'] for c in claims if PRODUCT_BY_ID[c['policy_product_id']]['benefit_type']=='FIXED'),
                            'claims_pending_minor':sum(c['approved_minor']-c['paid_minor'] for c in claims),
                            'out_of_pocket_minor':max(0,-(e['outcome'] or {}).get('cash_delta_minor',0)-paid),
                            'premiums_to_date_minor':-cats.get('PREMIUM',{}).get('amount_minor',0)})
    liquid=r['balances']['cash_minor']+r['balances']['savings_minor']
    essential=max(1,r['living_minor']+r['support_minor']);salary=r['salary_minor']*12
    premiums=sum(p['premium_minor'] for p in r['policies'] if p['status'] in ('ACTIVE','WAITING','GRACE'))
    active=sum(p['coverage_minor'] for p in r['policies'] if p['status']=='ACTIVE' and p['product_id'] in ('MEDICAL','ACCIDENT','CRITICAL_ILLNESS'))
    debt=money(r)['loan_minor']+money(r)['bill_minor']
    pre_ids=[x['id'] for x in r['ledger'] if x['category']=='PREMIUM'][-4:]
    lost=[x['id'] for x in r['events'] if x.get('outcome')][-4:]
    dimensions=[
        ('LIQUIDITY',min(100,liquid*100//(essential*6)),'可立即動用的資金與必要支出相比；六個月是教學參考。',lost),
        ('COVERAGE',min(100,active*100//max(1,r['salary_minor']*8)),'保障需求受收入與既有風險影響；不能以保單張數評分。',[p['id'] for p in r['policies']][-4:]),
        ('PREMIUM_AFFORDABILITY',max(0,100-premiums*900//max(1,salary)) if salary>0 else (100 if premiums==0 else None),
             '保費需能持續負擔；退休後沒有工作收入時不硬算保費收入比。',pre_ids),
        ('DEBT_RESILIENCE',max(0,100-debt*100//max(1,salary*2)) if salary>0 else (100 if debt==0 else 15),
             '借款、未付帳單與收入／退休狀態一起檢視。',[l['id'] for l in r['loans']][-4:]),
        ('LIFE_QUALITY',r['quality'],'將旅行、家人相處與壓力選擇納入評價。',lost)]
    return {'run_id':r['id'],'status':'READY','from_date':'2026-01-01','to_date':sim_date(r),
        'ending_reason':r['end_reason'],'opening_net_worth_minor':money({**r,**r['initial']})['net_worth_minor'],
        'ending_net_worth_minor':money(r)['net_worth_minor'],'categories':list(cats.values()),'coverage_effects':effects,
        'estate_benefits_approved_minor':r.get('estate_benefits_approved_minor',0),
        'dimensions':[{'code':code,'score':score,'explanation':reason,'evidence_ids':ids,
             'confidence':'HIGH' if ids else 'MEDIUM'} for code,score,reason,ids in dimensions],
        'timeline':[{'id':e['id'],'date':e['occurred_on'],'title':e['title'],'event_id':e['id'],
                     'kind':'EVENT','snapshot_id':next((s['point_id'] for s in r['snapshots'] if s['at_index']==e['at_index']),None)} for e in r['events']]}
def final_report(c):
    reports=[report(r) for r in c['runs']]
    last=reports[-1];improvement=last['ending_net_worth_minor']-reports[0]['ending_net_worth_minor']
    metric={d['code']:d for d in last['dimensions']}
    candidates=[d for d in last['dimensions'] if d['score'] is not None]
    ranked=sorted(candidates,key=lambda d:d['score'])
    display={'LIQUIDITY':'緊急預備金','COVERAGE':'保障是否適合','PREMIUM_AFFORDABILITY':'保費持續負擔',
             'DEBT_RESILIENCE':'債務承受能力','LIFE_QUALITY':'生活品質'}
    suggestions={'LIQUIDITY':'在可負擔範圍內，先保留可立即支出的生活預備金。',
                 'COVERAGE':'先核對需求與等待期，再選能持續繳費的保障。',
                 'PREMIUM_AFFORDABILITY':'減少對生活資金造成壓力的固定保費。',
                 'DEBT_RESILIENCE':'比較貸款利息與急用資金，避免持續借新還舊。',
                 'LIFE_QUALITY':'在財務可負擔時安排旅行、陪伴及休息。'}
    strengths=[{'title':display[d['code']],'explanation':d['explanation']+f' 本輪 {d["score"]} 分。',
        'evidence_ids':d['evidence_ids'],'alternative_action':None,'uncertainty':'MEDIUM'} for d in ranked[-2:]]
    improvements=[{'title':display[d['code']],'explanation':d['explanation']+f' 本輪 {d["score"]} 分。',
        'evidence_ids':d['evidence_ids'],'alternative_action':suggestions[d['code']],
        'uncertainty':'HIGH' if not d['evidence_ids'] else 'MEDIUM'} for d in ranked[:2]]
    if not strengths:strengths=[{'title':'完成三輪人生','explanation':'可回看三輪的財務與保障選擇。',
        'evidence_ids':[],'alternative_action':None,'uncertainty':'HIGH'}]
    unique_events=[set(e['card_id'] for e in r['events']) for r in c['runs']]
    all_same=all(events==unique_events[0] for events in unique_events[1:])
    first_net=reports[0]['ending_net_worth_minor'];last_net=reports[-1]['ending_net_worth_minor']
    outcomes=['三輪已支付理賠額 '+str(sum(x['paid_minor'] for r in c['runs'] for x in r['claims'])//100)+' 元，總保費 '+
       str(-sum(x['amount_minor'] for r in c['runs'] for x in r['ledger'] if x['category']=='PREMIUM')//100)+' 元；勿將未入帳理賠當作現金。']
    reason='三輪遭遇的事件不完全相同，差額混有運氣與人生長度差異。' if not all_same else '事件相近，仍應同時比較等待期與生活品質。'
    return {'id':uid(),'campaign_id':c['id'],'status':'READY','job_id':None,'run_ids':[r['id'] for r in c['runs']],
        'strengths':strengths,'improvements':improvements,
        'comparison_notes':[f'第三輪與首輪期末淨資產差額 {improvement//100:,} 元。{reason}',
             f'第三輪生活品質指數 {c["runs"][-1]["quality"]}／100。',*outcomes],
        'learning_topics':['reserve','claim','budget','portfolio'],'generated_at':now(),'ruleset_version':CONTENT_VERSION}
