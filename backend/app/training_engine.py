"""Course-scoped training simulation. Never mutates the legacy life engine."""
import copy,hashlib,random
from . import training_catalog as catalog

def integer(v,low,high):
 if type(v) is not int or not low<=v<=high:raise ValueError('INVALID_INPUT')
 return v

def plan(course,seed):
 rng=random.Random(f'{seed}:lesson');rules=course['rules'];pool=course['events'];chosen=[]
 extra=min(2,rules['emphasis_multiplier']-1) if rules['emphasis_topic']!='NONE' else 0
 for _ in range(min(8,max(3,len(pool)+extra))):
  # Cover selected lessons first. Extra weighted practice follows only after
  # coverage, so a normal six-lesson course does not silently omit a topic.
  candidates=[e for e in pool if not any(x['id']==e['id'] for x in chosen)]
  if not candidates:candidates=[e for e in pool if sum(x['id']==e['id'] for x in chosen)<2 and (not chosen or e['id']!=chosen[-1]['id'])] or pool
  weights=[rules['emphasis_multiplier'] if e['topic']==rules['emphasis_topic'] else 1 for e in candidates]
  chosen.append(copy.deepcopy(rng.choices(candidates,weights=weights,k=1)[0]))
 if rules['guaranteed_topic']:
  candidate=next((e for e in pool if e['topic']==rules['emphasis_topic']),None)
  if candidate and not any(e['topic']==candidate['topic'] for e in chosen):chosen[len(chosen)//2]=copy.deepcopy(candidate)
 return [{'month':max(1,(i+1)*rules['horizon_months']//(len(chosen)+1)),'template':e} for i,e in enumerate(chosen)]

def create(course,seed,event_plan=None):
 course=copy.deepcopy(course)
 refs={x for e in course['events'] for x in e['source_ids']}|{p['source']['id'] for p in course['products']}
 course['sources']={k:v for k,v in course['sources'].items() if k in refs}
 rules=course['rules'];salary=rules['salary_minor'];living=salary*rules['living_bps']//10000
 return {'version':1,'status':'PLAYING','month':0,'age':30,'location':'HOME','cash_minor':living*rules['reserve_months'],'savings_minor':0,
  'debt_minor':0,'unpaid_minor':0,'living_minor':living,'salary_minor':salary,'lifestyle':'BALANCED','quality':55,'prices':{s['id']:10000 for s in catalog.STOCKS},
  'holdings':{},'cost_basis':{},'price_history':{s['id']:[10000] for s in catalog.STOCKS},'policies':[],'claims':[],
  'history':[],'ledger':[],'pending':None,'next_event':0,'target_month':None,'turn':0,'_seed':seed,'_course':copy.deepcopy(course),
  '_plan':copy.deepcopy(event_plan) if event_plan is not None else plan(course,seed),'_stress_anchor':{},'stock_views':[]}

def liquidity(r):return r['cash_minor']+r['savings_minor']
def record(r,kind,amount,text):r['ledger'].append({'month':r['month'],'kind':kind,'amount_minor':amount,'description':text})
def credit(r,value,kind,text):r['cash_minor']+=value;record(r,kind,value,text)
def pay(r,value,kind,text,allow_bill=False):
 if value<0:raise ValueError('INVALID_INPUT')
 if not allow_bill and value>liquidity(r):raise ValueError('INSUFFICIENT_FUNDS')
 remaining=value
 for key in ['cash_minor','savings_minor']:
  used=min(r[key],remaining);r[key]-=used;remaining-=used
 if remaining:r['unpaid_minor']+=remaining
 record(r,kind,-value,text)

def balances(r):
 stocks=sum(q*r['prices'][sid] for sid,q in r['holdings'].items())
 accounts=sum(p['account_minor'] for p in r['policies'] if p['status']=='ACTIVE')
 return {'cash_minor':r['cash_minor'],'savings_minor':r['savings_minor'],'liquidity_minor':liquidity(r),'stocks_minor':stocks,
  'policy_accounts_minor':accounts,'debt_minor':r['debt_minor'],'unpaid_minor':r['unpaid_minor'],
  'receivables_minor':sum(c['approved_minor'] for c in r['claims'] if c['status']=='APPROVED'),
  'net_worth_minor':liquidity(r)+stocks+accounts-r['debt_minor']-r['unpaid_minor']}

def public(r):
 v={k:copy.deepcopy(x) for k,x in r.items() if not k.startswith('_') and k not in ('pending','next_event','target_month','cost_basis')}
 v['balances']=balances(r);v['horizon_months']=r['_course']['rules']['horizon_months'];v['course_title']=r['_course']['title']
 v['market_notice']='已設定市場下跌壓力情境，投資保單的連結部位也會受影響。' if r['_course']['rules']['market']!='NORMAL' else '市場含多空週期；前五檔為固定逆風組，並非保證獲利。'
 v['products']=copy.deepcopy(r['_course']['products']);v['stocks']=[{**s,'price_minor':r['prices'][s['id']]} for s in catalog.STOCKS]
 v['course_version']=r['_course']['revision'];v['scenario_notice']='教材重點以來源文件核對；所有交易金額、費用與市場路徑為遊戲假設。'
 refs={p['source']['id'] for p in r['_course']['products']}|{id for e in r['history'] for id in e['source_ids']}
 if r['pending']:refs.update(r['pending']['source_ids'])
 v['sources']={id:{**r['_course']['sources'][id],'text':r['_course']['sources'][id].get('text','')[:500]} for id in refs}
 if r['pending']:
  e=r['pending'];v['event']={k:copy.deepcopy(x) for k,x in e.items() if k not in ('correct_id','explanation','loss_minor','loss_kind')}
 else:v['event']=None
 v['report']=report(r) if r['status']=='ENDED' else None
 return v

def monthly(r):
 r['month']+=1;m=r['month'];rules=r['_course']['rules'];rng=random.Random(f'{r["_seed"]}:market:{m}')
 cycle=random.Random(f'{r["_seed"]}:cycle:{m//18}').choice([-100,-50,0,45,75])
 market=int(rng.gauss(0,340))+cycle
 if rules['market']=='DOWNTURN' and rules['stress_start']<=m<=rules['stress_end']:market-=180
 if rng.random()<.025:market-=rng.randint(900,1800)
 old=r['prices'].copy()
 for i,s in enumerate(catalog.STOCKS):
  change=int(market*s['beta_bps']/1000+s['drift_bps']/12+random.Random(f'{r["_seed"]}:{s["id"]}:{m}').gauss(0,s['vol_bps']/3.46))
  price=max(100,old[s['id']]*(10000+max(-2500,min(1800,change)))//10000)
  if rules['market']=='GUARANTEED_DROP' and rules['stress_start']<=m<=rules['stress_end']:
   anchor=r['_stress_anchor'].setdefault(s['id'],old[s['id']]);step=m-rules['stress_start']+1;total=rules['stress_end']-rules['stress_start']+1
   # Fixed cumulative loss for every exposed equity, independent of ownership.
   price=max(100,anchor*(10000-rules['drop_bps']*step//total)//10000)
  r['prices'][s['id']]=price;r['price_history'][s['id']].append(price)
  if m%12==0 and r['holdings'].get(s['id']):credit(r,r['holdings'][s['id']]*price*s['dividend_bps']//10000,'DIVIDEND','股票模擬股利')
 equity_return=sum((r['prices'][s]/old[s]-1) for s in old)/len(old)
 for p in r['policies']:
  if p['status']!='ACTIVE':continue
  if p['kind'] in ('INVESTMENT_LIFE','ANNUITY'):
   before=p['account_minor'];p['account_minor']=max(0,round(before*(1+equity_return*p['equity_bps']/10000)))
   fee=min(p['account_minor'],p['monthly_fee_minor']);p['account_minor']-=fee;p['fees_paid_minor']+=fee
   record(r,'POLICY_FEE',-fee,'投資帳戶管理與保障成本（遊戲假設）')
   if not p['account_minor']:p['status']='LAPSED'
  elif m-p['issued_month']>=12 and (m-p['issued_month'])%12==0:
   if liquidity(r)>=p['premium_minor']:pay(r,p['premium_minor'],'PREMIUM','年度模擬保費')
   else:p['status']='LAPSED'
 for c in r['claims']:
  if c['status']=='APPROVED' and c['due_month']<=m:
   c['status']='PAID';credit(r,c['approved_minor'],'CLAIM','模擬理賠入帳')
   policy=next((p for p in r['policies'] if p['id']==c['policy_id']),None)
   if policy and policy['status']=='CLAIM_PENDING':policy['status']='PAID_OUT'
 credit(r,r['salary_minor'],'SALARY','每月工作收入')
 pay(r,r['living_minor'],'LIVING','租屋、生活與交通固定支出',True)
 if r['debt_minor']:
  interest=r['debt_minor']*600//120000;r['debt_minor']+=interest;record(r,'INTEREST',-interest,'借款利息併入負債（遊戲假設）')
 if r['savings_minor']:
  interest=r['savings_minor']*80//120000;r['savings_minor']+=interest;record(r,'INTEREST',interest,'模擬活存月息')
 r['quality']=max(0,min(100,r['quality']+{'BASIC':-1,'BALANCED':0,'COMFORT':1}[r['lifestyle']]))

def advance(r):
 if r['status']!='PLAYING' or r['location']!='HOME':raise ValueError('ACTION_NOT_ALLOWED')
 r['turn']+=1;r['target_month']=min(r['_course']['rules']['horizon_months'],r['month']+random.Random(f'{r["_seed"]}:dice:{r["turn"]}').randint(1,6))
 resume(r)

def resume(r):
 while r['month']<r['target_month']:
  monthly(r)
  if r['next_event']<len(r['_plan']) and r['_plan'][r['next_event']]['month']<=r['month']:
   e=copy.deepcopy(r['_plan'][r['next_event']]['template']);e['instance_id']=hashlib.sha256(f'{r["turn"]}:{r["next_event"]}:{r["_seed"]}'.encode()).hexdigest()[:24]
   # Stable per encounter, independent of market RNG. AI often puts every
   # correct answer first; learners should decide from content, not position.
   random.Random(f'{e["instance_id"]}:choices').shuffle(e['choices'])
   r['pending']=e;r['status']='EVENT';return
 r['status']='ENDED' if r['month']>=r['_course']['rules']['horizon_months'] else 'PLAYING'

def decision(r,choice):
 if r['status']!='EVENT':raise ValueError('ACTION_NOT_ALLOWED')
 e=r['pending']
 if choice not in {c['id'] for c in e['choices']}:raise ValueError('INVALID_INPUT')
 loss=e['loss_minor']
 if loss:pay(r,loss,e['loss_kind'],'事件必要支出（遊戲假設）',True)
 row={'event_id':e['instance_id'],'title':e['title'],'month':r['month'],'topic':e['topic'],'choice_id':choice,
  'correct':choice==e['correct_id'],'explanation':e['explanation'],'source_ids':e['source_ids'],
  'loss_minor':loss,'loss_kind':e['loss_kind'],'claim_notice':'符合條件的模擬保單可申請理賠，核准後仍須等待入帳。' if loss or e['loss_kind']=='TERM_LIFE' else ''}
 r['history'].append(row);r['status']='RESULT';r['next_event']+=1

def product(r,id):
 p=next((x for x in r['_course']['products'] if x['id']==id),None)
 if not p:raise ValueError('NOT_FOUND')
 return p

def financial(r,action,p):
 if r['status'] not in ('PLAYING','RESULT'):raise ValueError('ACTION_NOT_ALLOWED')
 if r['location']!='FINANCE' and action!='CLAIM':raise ValueError('ACTION_NOT_ALLOWED')
 n=lambda key,lo=1,hi=10000000000:integer(p.get(key),lo,hi)
 if action in ('STOCK_BUY','STOCK_SELL'):
  sid=p.get('stock_id');qty=n('quantity',1,100000)
  if sid not in r['prices']:raise ValueError('INVALID_INPUT')
  gross=r['prices'][sid]*qty;fee=max(100,gross*30//10000)
  if action=='STOCK_BUY':
   pay(r,gross+fee,'STOCK_BUY','購入股票及 0.3% 模擬交易費');r['holdings'][sid]=r['holdings'].get(sid,0)+qty
   r['cost_basis'][sid]=r['cost_basis'].get(sid,0)+gross+fee
  else:
   total=r['holdings'].get(sid,0)
   if total<qty:raise ValueError('INSUFFICIENT_SHARES')
   r['cost_basis'][sid]=r['cost_basis'].get(sid,0)*(total-qty)//total;r['holdings'][sid]=total-qty
   credit(r,gross-fee,'STOCK_SELL','出售股票扣 0.3% 模擬交易費')
  return {'gross_minor':gross,'fees_minor':fee}
 if action in ('SAVE','WITHDRAW','BORROW','REPAY','PAY_BILL'):
  amount=n('amount_minor')
  if action=='SAVE':
   if amount>r['cash_minor']:raise ValueError('INSUFFICIENT_CASH')
   r['cash_minor']-=amount;r['savings_minor']+=amount
  elif action=='WITHDRAW':
   if amount>r['savings_minor']:raise ValueError('INSUFFICIENT_SAVINGS')
   r['savings_minor']-=amount;r['cash_minor']+=amount
  elif action=='BORROW':
   if amount+r['debt_minor']>r['salary_minor']*6:raise ValueError('BORROW_LIMIT')
   r['debt_minor']+=amount;credit(r,amount,'BORROW','借款本金，不是收入')
  else:
   key='debt_minor' if action=='REPAY' else 'unpaid_minor'
   if amount>r[key]:raise ValueError('REPAY_EXCEEDS_DEBT' if action=='REPAY' else 'PAYMENT_EXCEEDS_BILL')
   pay(r,amount,action,'清償負債／未付支出');r[key]-=amount
  return {'amount_minor':amount,'fees_minor':0}
 if action=='POLICY_BUY':
  v=product(r,p.get('product_id'));a=v['simulation'];investment=v['kind'] in ('INVESTMENT_LIFE','ANNUITY')
  if any(x['product_id']==v['id'] and x['status']=='ACTIVE' for x in r['policies']):raise ValueError('POLICY_EXISTS')
  amount=n('amount_minor',100000,100000000) if investment else a['premium_minor']
  fee=amount*a['entry_fee_bps']//10000 if investment else 0
  pay(r,amount,'PREMIUM','保費／投資款（遊戲假設）')
  r['policies'].append({'id':hashlib.sha256(f'{r["_seed"]}:{len(r["policies"])}'.encode()).hexdigest()[:24],
   'product_id':v['id'],'name':v['name'],'kind':v['kind'],'status':'ACTIVE','issued_month':r['month'],
   'account_minor':amount-fee if investment else 0,'premium_minor':amount,'fees_paid_minor':fee,
   'face_minor':a['face_minor'],'equity_bps':a['equity_bps'],'monthly_fee_minor':a['monthly_fee_minor'],
   'withdrawal_fee_bps':a['withdrawal_fee_bps'],'waiting_months':a['waiting_months'] if v['kind']=='MEDICAL' else 0,
   'claim_delay_months':a['claim_delay_months']})
  return {'amount_minor':amount,'fees_minor':fee,'account_minor':amount-fee if investment else 0}
 if action in ('POLICY_WITHDRAW','POLICY_SURRENDER','POLICY_ALLOCATE'):
  policy=next((x for x in r['policies'] if x['id']==p.get('policy_id') and x['status']=='ACTIVE'),None)
  if not policy or policy['kind'] not in ('INVESTMENT_LIFE','ANNUITY'):raise ValueError('POLICY_NOT_ELIGIBLE')
  if action=='POLICY_ALLOCATE':policy['equity_bps']=n('equity_bps',0,10000);return {'fees_minor':0}
  amount=policy['account_minor'] if action=='POLICY_SURRENDER' else n('amount_minor')
  if amount>policy['account_minor']:raise ValueError('POLICY_ACCOUNT_INSUFFICIENT')
  fee=amount*policy['withdrawal_fee_bps']//10000;policy['account_minor']-=amount;policy['fees_paid_minor']+=fee
  if not policy['account_minor']:policy['status']='SURRENDERED'
  credit(r,amount-fee,'POLICY_WITHDRAW','帳戶提領／解約扣費（遊戲假設）')
  return {'amount_minor':amount,'fees_minor':fee,'coverage_notice':'帳戶減少，保障與後續成本須重新核對；遊戲不代替正式試算。'}
 if action=='CLAIM':
  e=next((x for x in r['history'] if x['event_id']==p.get('event_id')),None)
  policy=next((x for x in r['policies'] if x['id']==p.get('policy_id')),None)
  if not e or not policy or any(c['event_id']==e['event_id'] for c in r['claims']):raise ValueError('CLAIM_NOT_ELIGIBLE')
  if policy['status']!='ACTIVE' or policy['kind']!=e['loss_kind'] or policy['issued_month']+policy['waiting_months']>e['month']:raise ValueError('CLAIM_NOT_ELIGIBLE')
  amount=policy['face_minor'] if policy['kind']=='TERM_LIFE' else min(e['loss_minor'],policy['face_minor'])
  if not amount:raise ValueError('CLAIM_NOT_ELIGIBLE')
  if policy['kind']=='TERM_LIFE':policy['status']='CLAIM_PENDING'
  r['claims'].append({'event_id':e['event_id'],'policy_id':policy['id'],'approved_minor':amount,'status':'APPROVED','due_month':r['month']+max(1,policy['claim_delay_months'])})
  return {'approved_minor':amount,'fees_minor':0,'notice':'核准不是入帳；需推進至給付月份。'}
 raise ValueError('INVALID_INPUT')

def quote(r,action,params):
 twin=copy.deepcopy(r);before=balances(twin);result=financial(twin,action,params);after=balances(twin)
 return {'action':action,'params':copy.deepcopy(params),'before':before,'after':after,'result':result,
  'notice':'先檢查費用與可用資金；此確認單使用課程固定的遊戲假設。','run_version':r['version']}

def report(r):
 n=len(r['history']);correct=sum(h['correct'] for h in r['history'])
 return {'score':round(correct*100/max(1,n)),'decisions':n,'correct':correct,'balances':balances(r),
  'topics':sorted(set(h['topic'] for h in r['history'])),'lessons':copy.deepcopy(r['history']),
  'selection_feedback':'配置曾涵蓋後十五檔標的；仍應比較風險與資金需求。' if any(s not in {x['id'] for x in catalog.STOCKS[:5]} for s in r['holdings']) else '目前未配置後十五檔標的；排序不是適合度或報酬保證。',
  'notice':'學習分數依條款與風險判斷，不以買最多保單或賺最多錢決定。'}
