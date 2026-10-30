"""Versioned authoring, private materials and reproducible classroom sessions."""
import copy,hashlib,json,re,secrets,time
from urllib.parse import urlsplit
from . import engine,store,training_catalog as catalog,training_engine as sim
from .errors import UserError,message_for

def init_schema(db):
 db.executescript('''
 CREATE TABLE IF NOT EXISTS training_admins(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE);
 CREATE TABLE IF NOT EXISTS training_materials(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,kind TEXT NOT NULL,raw BLOB NOT NULL,body TEXT NOT NULL,created_at REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS training_material_owner ON training_materials(owner,created_at);
 CREATE TABLE IF NOT EXISTS training_products(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,body TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS training_courses(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE SET NULL,status TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS training_course_owner ON training_courses(owner,status);
 CREATE TABLE IF NOT EXISTS training_classes(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE SET NULL,code TEXT NOT NULL UNIQUE,
  body TEXT NOT NULL,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS training_runs(id TEXT PRIMARY KEY,class_id TEXT NOT NULL REFERENCES training_classes(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,body TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(class_id,user_id));
 CREATE INDEX IF NOT EXISTS training_runs_user ON training_runs(user_id,created_at);
 CREATE TABLE IF NOT EXISTS training_ai_jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,body TEXT NOT NULL,created_at REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS training_ai_owner ON training_ai_jobs(owner,created_at);
 CREATE TABLE IF NOT EXISTS training_audit(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id) ON DELETE SET NULL,action TEXT NOT NULL,created_at TEXT NOT NULL);
 ''')
 if not db.execute('SELECT 1 FROM training_courses WHERE id=?',('cardif-intro-20261027',)).fetchone():
  c=validate_course(db,None,{**catalog.base_course(),'reviewed':True})
  c.update(id='cardif-intro-20261027',revision=catalog.VERSION,status='PUBLISHED',version=1,mode='REVIEWED_SAMPLE',created_at=engine.now(),
   review_notice='專案示範教案，未經巴黎人壽內部審核；實際商品仍以正式條款及講師審核為準。')
  db.execute('INSERT INTO training_courses VALUES(?,NULL,?,?,?)',(c['id'],'PUBLISHED',store.j(c),c['created_at']))

def require(flag,code='INVALID_INPUT',message=None,details=None):
 if not flag:
  if message:raise UserError(code,message,details)
  raise ValueError(code)
def text(v,min_=1,max_=200,label='欄位'):
 require(isinstance(v,str) and min_<=len(v.strip())<=max_,'FIELD_INVALID',f'{label}須為 {min_} 至 {max_} 字。',{'field':label,'min':min_,'max':max_})
 return v.strip()
def url(v):
 if not v:return ''
 require(isinstance(v,str) and len(v)<2000,'INVALID_SOURCE_URL')
 try:p=urlsplit(v)
 except ValueError:raise ValueError('INVALID_SOURCE_URL')
 require(p.scheme in ('http','https') and p.hostname and not p.username and not p.password,'INVALID_SOURCE_URL');return v

def require_ready(material,name='所選教材'):
 state=material.get('status')
 code={'PARSING':'MATERIAL_PARSING','NEEDS_OCR':'MATERIAL_NEEDS_OCR','FAILED':'MATERIAL_PARSE_FAILED'}.get(state,'MATERIAL_NOT_READY')
 require(state=='READY',code,f'教材「{name}」：{message_for(code)}')

def admin(db,u):return bool(u and u['verified'] and db.execute('SELECT 1 FROM training_admins WHERE user_id=?',(u['id'],)).fetchone())
def audit(db,uid,action):db.execute('INSERT INTO training_audit VALUES(?,?,?,?)',(engine.uid(),uid,action,engine.now()))
def all_products(db,uid):
 return catalog.products()+[json.loads(r[0]) for r in db.execute('SELECT body FROM training_products WHERE owner=?',(uid,))] if uid else catalog.products()

MAX_EVENT_SOURCES=8

def rules(value):
 require(isinstance(value,dict),'RULES_INVALID');r={**catalog.base_course()['rules'],**value}
 require(not set(value)-set(catalog.base_course()['rules']),'RULES_INVALID')
 limits={'horizon_months':('課程月份',12,120,1),'salary_minor':('每月收入（元）',1000000,20000000,100),
  'living_bps':('生活支出占收入（%）',5000,8500,100),'reserve_months':('初始預備金（月生活費）',1,4,1),
  'drop_bps':('累計跌幅（%）',1000,6000,100),'stress_start':('壓力起始月',1,100,1),
  'stress_end':('壓力結束月',2,120,1),'emphasis_multiplier':('抽樣權重',1,5,1)}
 for key,(label,lo,hi,scale) in limits.items():
  require(type(r[key]) is int and lo<=r[key]<=hi,'FIELD_OUT_OF_RANGE',f'{label}須介於 {lo//scale} 至 {hi//scale}，'+('最多小數點後 2 位。' if scale==100 else '請填寫整數。'),{'field':'rules.'+key,'min':lo,'max':hi})
 require(r['market'] in ('NORMAL','DOWNTURN','GUARANTEED_DROP'),'RULES_INVALID','請選擇清單中的市場情境。')
 require(r['stress_start']<r['stress_end']<=r['horizon_months'],'STRESS_PERIOD_INVALID')
 require(type(r['guaranteed_topic']) is bool,'RULES_INVALID')
 require(r['emphasis_topic'] in {'NONE'}|{e['topic'] for e in catalog.EVENTS},'RULES_INVALID','請選擇清單中的加強主題。')
 require(not r['guaranteed_topic'] or r['emphasis_topic']!='NONE','EMPHASIS_REQUIRED')
 return r

def validate_events(events,sources):
 require(isinstance(events,list) and 1<=len(events)<=12,'EVENT_COUNT_INVALID')
 result=[];ids=set()
 for i,e in enumerate(events):
  require(isinstance(e,dict),'INVALID_INPUT')
  context=f'第 {i+1} 則情境'+(f'「{e["title"][:70]}」' if isinstance(e.get('title'),str) and e['title'] else '')
  id=text(e.get('id'),1,40,context+'識別資料');require(id not in ids,'FIELD_INVALID',context+'的識別資料重複，請移除重複情境後重新加入範本。');ids.add(id)
  require(e.get('topic') in {x['topic'] for x in catalog.EVENTS},'FIELD_INVALID',context+'：請選擇清單中的主題。');choices=e.get('choices')
  require(isinstance(choices,list) and 2<=len(choices)<=4,'CHOICES_INVALID',context+'須有 2 至 4 個選項。')
  require(all(isinstance(x,dict) for x in choices),'CHOICES_INVALID',context+'的選項格式不正確。')
  cs=[{'id':text(x.get('id'),1,20,context+'選項識別'),'label':text(x.get('label'),1,140,context+f'第 {n+1} 項選項文字')} for n,x in enumerate(choices)]
  require(len({x['id'] for x in cs})==len(cs) and e.get('correct_id') in {x['id'] for x in cs},'CHOICES_INVALID',context+'須使用不同的選項識別，並指定一項現有選項為教學答案。')
  refs=e.get('source_ids');details={'field':f'events.{i}.source_ids','event_index':i,'max':MAX_EVENT_SOURCES,'count':len(refs) if isinstance(refs,list) else 0}
  require(isinstance(refs,list) and len(refs)>0,'SOURCE_REQUIRED',context+'至少要選擇 1 項教學依據。',details)
  require(len(refs)<=MAX_EVENT_SOURCES,'SOURCE_LIMIT_EXCEEDED',context+f'已選 {len(refs)} 項教學依據，最多 {MAX_EVENT_SOURCES} 項。請取消部分引用後再儲存。',details)
  require(all(isinstance(x,str) and x in sources for x in refs),'SOURCE_NOT_AVAILABLE',context+'的部分引用不在目前教案內。請重新選用相關商品／教材，或取消已失效的引用。',details)
  require(len(set(refs))==len(refs),'SOURCE_DUPLICATE',context+'重複引用相同來源，請移除重複項目。',details)
  loss=e.get('loss_minor',0);kind=e.get('loss_kind','NONE')
  require(type(loss) is int and 0<=loss<=50000000,'EVENT_EFFECT_INVALID',context+'的必要支出須為 0 至 500,000 元。')
  require(kind in ('NONE','LIVING','MEDICAL','LIABILITY','TERM_LIFE') and (not loss or kind!='NONE'),'EVENT_EFFECT_INVALID',context+'有必要支出時須選擇對應支出類型。')
  result.append({'id':id,'topic':e['topic'],'title':text(e.get('title'),1,70,context+'名稱'),'prompt':text(e.get('prompt'),1,400,context+'劇情與提問'),
   'lesson':text(e.get('lesson'),1,300,context+'短教學'),'explanation':text(e.get('explanation'),1,500,context+'短回饋'),'choices':cs,'correct_id':e['correct_id'],
   'source_ids':refs,'loss_minor':loss,'loss_kind':kind})
 return result

def validate_course(db,uid,b):
 pids=b.get('product_ids');require(isinstance(pids,list) and 1<=len(pids)<=8 and all(isinstance(x,str) for x in pids) and len(pids)==len(set(pids)),'PRODUCT_SELECTION_INVALID')
 available={p['id']:p for p in all_products(db,uid)};require(all(id in available for id in pids),'PRODUCT_NOT_AVAILABLE')
 ps=[copy.deepcopy(available[id]) for id in pids];sources=copy.deepcopy(catalog.SOURCES)
 for p in ps:sources[p['source']['id']]=p['source']
 mids=b.get('material_ids',[]);require(isinstance(mids,list) and len(mids)<=10 and all(isinstance(x,str) for x in mids) and len(mids)==len(set(mids)),'MATERIAL_SELECTION_INVALID')
 for mid in mids:
  row=db.execute('SELECT body,name FROM training_materials WHERE id=? AND owner=?',(mid,uid)).fetchone();require(row,'NOT_FOUND')
  m=json.loads(row[0]);require_ready(m,row['name'])
  for section in m['sections']:sources[section['id']]={'id':section['id'],'title':row['name'],'locator':section['label'],'text':section['text'],'url':url(m.get('source_url',''))}
 r=rules(b.get('rules',{}));events=validate_events(b.get('events',[]),sources)
 require(not r['guaranteed_topic'] or any(e['topic']==r['emphasis_topic'] for e in events),'TOPIC_NOT_IN_COURSE')
 unresolved=b.get('unresolved',[]);require(isinstance(unresolved,list) and len(unresolved)<=30 and all(isinstance(x,str) and len(x)<500 for x in unresolved),'UNRESOLVED_INVALID')
 return {'title':text(b.get('title'),1,100,'教案名稱'),'audience':text(b.get('audience'),1,100,'授課對象'),'instructions':text(b.get('instructions'),1,4000,'希望怎麼教'),
  'product_ids':pids,'products':ps,'material_ids':mids,'sources':sources,'rules':r,'events':events,'reviewed':b.get('reviewed') is True,
  'unresolved':unresolved,'mode':'MANUAL_TEMPLATE'}

def course(db,id):
 row=db.execute('SELECT * FROM training_courses WHERE id=?',(id,)).fetchone();require(row,'NOT_FOUND');return row,json.loads(row['body'])
def owned_course(db,uid,id):
 row,c=course(db,id);require(row['owner']==uid,'FORBIDDEN');return c
def save_course(db,uid,b,id=None):
 old=owned_course(db,uid,id) if id else None
 if old:require(old['status']=='DRAFT','PUBLISHED_IMMUTABLE');require(b.get('expected_version')==old['version'],'STALE_VERSION')
 c=validate_course(db,uid,b);c.update(id=id or engine.uid(),revision=engine.uid(),status='DRAFT',version=old['version']+1 if old else 1,
                                  created_at=old['created_at'] if old else engine.now())
 if old:db.execute('UPDATE training_courses SET body=? WHERE id=?',(store.j(c),id))
 else:db.execute('INSERT INTO training_courses VALUES(?,?,?,?,?)',(c['id'],uid,'DRAFT',store.j(c),c['created_at']))
 audit(db,uid,'COURSE_SAVE:'+c['id']);return c

def create_class(db,uid,b):
 row,c=course(db,b.get('course_id'));require(row['owner'] is None or row['owner']==uid,'FORBIDDEN');require(c['status']=='PUBLISHED','COURSE_NOT_PUBLISHED')
 code=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8))
 value={'id':engine.uid(),'code':code,'title':text(b.get('title'),1,100,'班次名稱'),'course_title':c['title'],'course_id':c['id'],
        'revision':c['revision'],'status':'OPEN','course':c,'scenario_seed':secrets.randbits(64),'created_at':engine.now()}
 value['_plan']=sim.plan(c,value['scenario_seed'])
 db.execute('INSERT INTO training_classes VALUES(?,?,?,?,?)',(value['id'],uid,code,store.j(value),value['created_at']));audit(db,uid,'CLASS_OPEN:'+value['id'])
 return class_view(value)
def class_view(c):return {k:v for k,v in c.items() if k not in ('course','scenario_seed','_plan')}

def join(db,u,code):
 require(u['verified'],'EMAIL_NOT_VERIFIED');require(isinstance(code,str) and re.fullmatch(r'[A-Za-z0-9]{8}',code.strip()),'CLASS_CODE_INVALID');code=code.strip().upper()
 row=db.execute('SELECT * FROM training_classes WHERE code=?',(code,)).fetchone();require(row,'CLASS_NOT_FOUND');c=json.loads(row['body'])
 old=db.execute('SELECT id,body FROM training_runs WHERE class_id=? AND user_id=?',(c['id'],u['id'])).fetchone()
 if old:return {'id':old['id'],'state':sim.public(json.loads(old['body']))}
 require(c['status']=='OPEN','CLASS_CLOSED')
 if '_plan' not in c:
  prior=db.execute('SELECT body FROM training_runs WHERE class_id=? ORDER BY created_at LIMIT 1',(c['id'],)).fetchone()
  c['_plan']=json.loads(prior[0])['_plan'] if prior else sim.plan(c['course'],c['scenario_seed'])
  db.execute('UPDATE training_classes SET body=? WHERE id=?',(store.j(c),c['id']))
 r=sim.create(c['course'],c['scenario_seed'],c['_plan']);id=engine.uid()
 db.execute('INSERT INTO training_runs VALUES(?,?,?,?,?)',(id,c['id'],u['id'],store.j(r),engine.now()));return {'id':id,'state':sim.public(r)}

def owned_run(db,uid,id):
 row=db.execute('SELECT * FROM training_runs WHERE id=? AND user_id=?',(id,uid)).fetchone();require(row,'NOT_FOUND');return json.loads(row['body'])
def action(db,u,id,b):
 r=owned_run(db,u['id'],id);require(b.get('expected_version')==r['version'],'STALE_VERSION');kind=b.get('action');p=b.get('params',{})
 require(isinstance(p,dict))
 if kind=='MOVE':
  require(r['status']=='PLAYING','ACTION_NOT_ALLOWED');require(p.get('location') in ('HOME','FINANCE','WORK'),'INVALID_INPUT');r['location']=p['location']
 elif kind=='ROLL':sim.advance(r)
 elif kind=='DECIDE':sim.decision(r,p.get('choice_id'))
 elif kind=='ACK':require(r['status']=='RESULT','ACTION_NOT_ALLOWED');r['pending']=None;sim.resume(r)
 elif kind=='LIFESTYLE':
  require(r['status']=='PLAYING','ACTION_NOT_ALLOWED');choice=p.get('lifestyle');require(choice in ('BASIC','BALANCED','COMFORT'))
  r['living_minor']=r['salary_minor']*r['_course']['rules']['living_bps']//10000*{'BASIC':75,'BALANCED':100,'COMFORT':140}[choice]//100;r['lifestyle']=choice
 else:
  require(b.get('confirmed') is True,'CONFIRMATION_REQUIRED');sim.financial(r,kind,p)
 r['version']+=1;db.execute('UPDATE training_runs SET body=? WHERE id=?',(store.j(r),id));return {'id':id,'state':sim.public(r)}

def class_report(db,uid,id):
 row=db.execute('SELECT body FROM training_classes WHERE id=? AND owner=?',(id,uid)).fetchone();require(row,'NOT_FOUND');c=json.loads(row[0]);learners=[];topics={}
 for row in db.execute('SELECT r.id,r.body,u.display_name FROM training_runs r JOIN users u ON u.id=r.user_id WHERE class_id=?',(id,)):
  r=json.loads(row['body']);rep=sim.report(r)
  learners.append({'id':row['id'],'name':row['display_name'],'status':r['status'],'month':r['month'],'score':rep['score'],'decisions':rep['decisions']})
  for e in r['history']:
   v=topics.setdefault(e['topic'],{'answered':0,'incorrect':0});v['answered']+=1;v['incorrect']+=not e['correct']
 return {'class':class_view(c),'learners':learners,'topics':topics,'completed':sum(x['status']=='ENDED' for x in learners),
         'notice':'評量用於授課回饋；不是實際投保資格、商品適合度或人事考核決定。'}
