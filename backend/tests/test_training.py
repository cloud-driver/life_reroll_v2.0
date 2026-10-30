"""Offline training acceptance tests; no production DB, mail or model service."""
import base64,copy,io,json,uuid,zipfile
import pytest
from fastapi.testclient import TestClient
from app import store,training_catalog as catalog,training_engine as sim,training_service as svc,training_materials as docs,training_jobs as jobs
from app.main import app
from test_game import game

@pytest.fixture
def teacher(game,monkeypatch):
 monkeypatch.setenv('LIFE_TRAINING_LLM_ENABLED','0')
 game.auth('teacher@example.test')
 with store.tx() as db:db.execute('INSERT INTO training_admins SELECT id FROM users WHERE email=?',('teacher@example.test',))
 return game

def call(g,m,p,b=None,status=200,key=None):return g.call(m,'/training'+p,b,status,key)[0]
def save(g,**patch):return call(g,'POST','/admin/courses',{**catalog.base_course(),**patch})
def publish(g,c):return call(g,'POST',f'/admin/courses/{c["id"]}/publish',{'expected_version':c['version']})
def classroom(g,c=None):
 c=c or publish(g,save(g,reviewed=True))
 return call(g,'POST','/admin/classes',{'title':'銀行理專授課','course_id':c['id']})
def join(g,c):return call(g,'POST','/join',{'code':c['code']})
def action(g,r,a,p=None,confirmed=False,key=None,status=200):return call(g,'POST',f'/runs/{r["id"]}/actions',{'expected_version':r['state']['version'],'action':a,'params':p or {},'confirmed':confirmed},status,key)
def quote(g,r,a,p):return call(g,'POST',f'/runs/{r["id"]}/quotes',{'expected_version':r['state']['version'],'action':a,'params':p})

def test_roles_verified_csrf_and_private_data(game):
 assert call(game,'GET','/capabilities')['llm']['enabled'] is False
 assert call(game,'GET','/catalog')['base_course'] is None
 call(game,'GET','/session',status=401)
 game.auth()
 assert call(game,'GET','/session')['is_instructor'] is False
 call(game,'GET','/admin/materials',status=403)
 call(game,'POST','/admin/courses',catalog.base_course(),403)
 assert game.client.post('/api/v1/training/join',json={'code':'ABCDEFGH'}).status_code==403
 with store.tx() as db:db.execute('UPDATE users SET verified=0')
 call(game,'POST','/join',{'code':'ABCDEFGH'},403)

def test_immutable_course_class_and_idempotent_commands(teacher):
 g=teacher;c=save(g);call(g,'POST',f'/admin/courses/{c["id"]}/publish',{'expected_version':c['version']},422)
 c=call(g,'PUT','/admin/courses/'+c['id'],{**c,'reviewed':True,'expected_version':c['version']});c=publish(g,c);cl=classroom(g,c);r=join(g,cl)
 old=json.dumps(r,sort_keys=True);q=quote(g,action(g,r,'MOVE',{'location':'FINANCE'}),'STOCK_BUY',{'stock_id':'STABLE','quantity':10})
 assert q['result']['fees_minor']==300 and q['after']['net_worth_minor']==q['before']['net_worth_minor']-300
 # Preview did not alter saved state.
 r=call(g,'GET','/runs/'+r['id']);assert r['state']['holdings']=={}
 key=str(uuid.uuid4());v=action(g,r,'STOCK_BUY',q['params'],True,key);again=action(g,r,'STOCK_BUY',q['params'],True,key)
 assert v==again and v['state']['holdings']['STABLE']==10
 action(g,r,'STOCK_BUY',q['params'],True,status=409)
 action(g,v,'STOCK_BUY',q['params'],False,status=422)
 call(g,'PUT','/admin/courses/'+c['id'],{**c,'expected_version':c['version']},409)
 new=call(g,'POST','/admin/courses/'+c['id']+'/clone',{});new=call(g,'PUT','/admin/courses/'+new['id'],{**new,'title':'下一版','expected_version':new['version']})
 assert call(g,'GET','/runs/'+r['id'])['state']['course_title']==c['title']
 assert new['status']=='DRAFT'
 call(g,'POST','/admin/classes/'+cl['id']+'/close',{})
 assert join(g,cl)['id']==r['id']
 report=call(g,'GET','/admin/classes/'+cl['id']+'/report');assert len(report['learners'])==1
 original=g.client;g.client=TestClient(app);g.csrf=None;g.auth('other@example.test');call(g,'POST','/join',{'code':cl['code']},409)
 call(g,'GET','/runs/'+r['id'],status=404);call(g,'GET','/admin/classes/'+cl['id']+'/report',status=403)
 g.client=original

def test_frozen_common_market_and_learner_no_answers(teacher):
 g=teacher;cl=classroom(g);one=join(g,cl)
 g.client=TestClient(app);g.csrf=None;g.auth('learner@example.test');two=join(g,cl)
 a=sim.create(catalog_course(),12);b=copy.deepcopy(a);b['holdings']['STABLE']=100
 for _ in range(12):sim.monthly(a);sim.monthly(b)
 assert a['prices']==b['prices']
 with store.tx(read_only=True) as db:
  raws=[json.loads(row[0]) for row in db.execute('SELECT body FROM training_runs WHERE class_id=?',(cl['id'],))]
 assert raws[0]['_plan']==raws[1]['_plan']
 assert call(g,'GET','/courses')[0].get('events') is None
 while two['state']['status']=='PLAYING':two=action(g,two,'ROLL')
 assert two['state']['status']=='EVENT' and 'correct_id' not in two['state']['event'] and 'loss_minor' not in two['state']['event']
 assert not any(k.startswith('_') for k in two['state'])

def catalog_course(**rules):
 c=catalog.base_course();c.update(products=catalog.products()[:3],sources=copy.deepcopy(catalog.SOURCES),revision='test');c['rules'].update(rules);return c

@pytest.mark.parametrize('field,value',[('horizon_months',4),('living_bps',100),('market','MAGIC'),('guaranteed_topic','true'),('drop_bps',True),('salary_minor',0),('stress_end',1)])
def test_invalid_rules(teacher,field,value):
 c=catalog.base_course();c['rules'][field]=value;call(teacher,'POST','/admin/courses',c,422)

def test_sources_review_and_missing_topic(teacher):
 c=catalog.base_course();c['events'][0]['source_ids']=['other-private-document'];call(teacher,'POST','/admin/courses',c,422)
 c=catalog.base_course();c['rules'].update(guaranteed_topic=True,emphasis_topic='LIABILITY');call(teacher,'POST','/admin/courses',c,422)
 c=catalog.base_course();c['rules'].update(guaranteed_topic=True,emphasis_topic='MARKET',emphasis_multiplier=5);c=save(teacher,**c)
 p=call(teacher,'POST','/admin/courses/'+c['id']+'/preview',{});assert p['samples']==p['with_topic']==200

@pytest.mark.parametrize('extension,raw,expected',[('txt','授課範本：先問資金用途。'.encode(),'READY'),('md',b'# teaching\nliquidity','READY'),('pdf',b'not-pdf','FAILED')])
def test_material_background_ingestion(teacher,extension,raw,expected):
 g=teacher;m=call(g,'POST','/admin/materials',{'name':'../lesson.'+extension,'data_base64':base64.b64encode(raw).decode()})
 jobs.POOL.submit(lambda:None).result(10)
 parsed=next(x for x in call(g,'GET','/admin/materials') if x['id']==m['id']);assert parsed['status']==expected
 assert not parsed['name'].startswith('..') and 'raw' not in parsed
 if expected=='READY':
  c=catalog.base_course();c['material_ids']=[m['id']];c['events'][0]['source_ids']=[parsed['sections'][0]['id']];v=save(g,**c)
  assert v['sources'][parsed['sections'][0]['id']]['text']
  assert save(g,**{**c,'reviewed':True})['reviewed']

def office(kind,text='保障與費用'):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  if kind=='docx':z.writestr('word/document.xml',f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:document>')
  else:z.writestr('ppt/slides/slide1.xml',f'<p:sld xmlns:p="x" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:t>{text}</a:t></p:sld>')
 return b.getvalue()

@pytest.mark.parametrize('kind',['docx','pptx'])
def test_office_text_and_bomb_limit(kind):
 assert docs.extract(kind,office(kind))[0]['text']=='保障與費用'
 with pytest.raises(ValueError):docs.extract(kind,office(kind,'x'*170000))
 with pytest.raises(ValueError):docs.extract(kind,b'badzip')

def test_pdf_scanned_encrypted_and_limits():
 from pypdf import PdfWriter
 out=io.BytesIO();w=PdfWriter();w.add_blank_page(width=100,height=100);w.write(out)
 assert docs.extract('pdf',out.getvalue())==[]
 out=io.BytesIO();w.encrypt('secret');w.write(out)
 with pytest.raises(ValueError,match='ENCRYPTED_DOCUMENT'):docs.extract('pdf',out.getvalue())
 with pytest.raises(ValueError):docs.decode('bad.exe','eA==')
 with pytest.raises(ValueError):docs.decode('data.txt','%%%')
 with pytest.raises(ValueError):docs.decode('data.txt',base64.b64encode(b'x'*(docs.MAX_BYTES+1)).decode())

def test_material_ownership_and_custom_product(teacher):
 g=teacher;m=call(g,'POST','/admin/materials',{'name':'lesson.txt','data_base64':base64.b64encode('合法授課來源'.encode()).decode()});jobs.POOL.submit(lambda:None).result(10)
 product=call(g,'POST','/admin/products',{'name':'內部保單練習','provider':'講師授權資料','kind':'MEDICAL','source_title':'課程教材','source_locator':'第一段','material_id':m['id'],'facts':['教學用等待期'],'reviewed':True})
 c=catalog.base_course();c['product_ids'].append(product['id']);assert save(g,**c)['products'][-1]['source']['material_id']==m['id']
 g.client=TestClient(app);g.csrf=None;g.auth('teacher2@example.test')
 with store.tx() as db:db.execute('INSERT INTO training_admins SELECT id FROM users WHERE email=?',('teacher2@example.test',))
 assert call(g,'GET','/admin/materials')==[]
 c['material_ids']=[m['id']];call(g,'POST','/admin/courses',c,422)
 c=catalog.base_course();c['material_ids']=[m['id']];call(g,'POST','/admin/courses',c,404)

def test_disabled_ai_never_connects_and_contract_is_bounded(teacher,monkeypatch):
 g=teacher;c=save(g)
 def forbidden(*a,**kw):raise AssertionError('External model must remain off')
 monkeypatch.setattr(jobs,'provider_generate',forbidden)
 j=call(g,'POST','/admin/ai-jobs',{'course_id':c['id']});assert j['status']=='WAITING_PROVIDER' and j['result'] is None
 call(g,'POST','/admin/ai-jobs/'+j['id']+'/retry',{},422)
 assert call(g,'GET','/admin/ai-jobs')[0]['status']=='WAITING_PROVIDER'
 valid={'contract_version':'training-author-v1','events':c['events'],'extracted_facts':[{'text':'費用需核對','source_id':'vul'}],'unresolved':['待講師核對']}
 assert jobs.validate_result(valid,c)['unresolved']
 for p in [{'contract_version':'wrong'},{'events':[dict(c['events'][0],source_ids=['made-up'])]},{'exec':'code'},{'extracted_facts':[{'text':'fake','source_id':'wrong'}]}]:
  with pytest.raises(ValueError):jobs.validate_result({**valid,**p},c)
 call(g,'POST','/admin/ai-jobs/'+j['id']+'/cancel',{})
 assert call(g,'GET','/admin/ai-jobs')[0]['status']=='CANCELLED'

def test_course_trial_does_not_count_as_class(teacher):
 g=teacher;c=save(g);r=call(g,'POST','/admin/courses/'+c['id']+'/trial',{})
 assert r['state']['status']=='PLAYING'
 assert call(g,'GET','/admin/classes')==[]
 assert action(g,r,'ROLL')['state']['month']>0

@pytest.mark.parametrize('kind,params',[('SAVE',{'amount_minor':100000}),('STOCK_BUY',{'stock_id':'TECH','quantity':10}),('POLICY_BUY',{'product_id':'CARDIF_VUL','amount_minor':1000000}),('BORROW',{'amount_minor':100000})])
def test_financial_quotes_conserve_assets_and_are_pure(kind,params):
 r=sim.create(catalog_course(),22);r['location']='FINANCE';before=copy.deepcopy(r);q=sim.quote(r,kind,params)
 assert before==r
 sim.financial(r,kind,params);assert sim.balances(r)==q['after']
 assert q['after']['net_worth_minor']==q['before']['net_worth_minor']-q['result']['fees_minor']

def test_policy_withdraw_allocate_surrender_and_expenses():
 r=sim.create(catalog_course(),11);r['location']='FINANCE';sim.financial(r,'POLICY_BUY',{'product_id':'CARDIF_VUL','amount_minor':1000000});p=r['policies'][0]
 assert p['account_minor']==970000 and p['fees_paid_minor']==30000
 before=sim.balances(r)['net_worth_minor'];sim.financial(r,'POLICY_WITHDRAW',{'policy_id':p['id'],'amount_minor':100000});assert sim.balances(r)['net_worth_minor']==before-1000
 sim.financial(r,'POLICY_ALLOCATE',{'policy_id':p['id'],'equity_bps':0});sim.monthly(r);assert p['account_minor']==860000
 sim.financial(r,'POLICY_SURRENDER',{'policy_id':p['id']});assert p['status']=='SURRENDERED' and p['account_minor']==0
 with pytest.raises(ValueError):sim.financial(r,'POLICY_WITHDRAW',{'policy_id':p['id'],'amount_minor':1})
 r['cash_minor']=0;r['savings_minor']=0;r['living_minor']=r['salary_minor']*2;sim.monthly(r);assert r['unpaid_minor']==r['salary_minor']

def test_claim_waiting_backdating_duplicate_and_payment():
 c=catalog_course();c['products']=catalog.products();r=sim.create(c,9);r['location']='FINANCE';sim.financial(r,'POLICY_BUY',{'product_id':'SIM_MEDICAL'});p=r['policies'][0]
 e={'event_id':'one','loss_kind':'MEDICAL','loss_minor':8000000,'month':1};r['history']=[e]
 with pytest.raises(ValueError,match='CLAIM_NOT_ELIGIBLE'):sim.financial(r,'CLAIM',{'policy_id':p['id'],'event_id':'one'})
 e['month']=2;r['month']=2;before=sim.balances(r);sim.financial(r,'CLAIM',{'policy_id':p['id'],'event_id':'one'});assert sim.balances(r)['liquidity_minor']==before['liquidity_minor'] and sim.balances(r)['receivables_minor']==8000000
 with pytest.raises(ValueError):sim.financial(r,'CLAIM',{'policy_id':p['id'],'event_id':'one'})
 sim.monthly(r);assert r['claims'][0]['status']=='PAID'
 r['history'].append(dict(e,event_id='two',loss_kind='LIABILITY'))
 with pytest.raises(ValueError):sim.financial(r,'CLAIM',{'policy_id':p['id'],'event_id':'two'})

def test_guaranteed_market_drop_applies_to_all_equity_and_insurance():
 c=catalog_course(market='GUARANTEED_DROP',stress_start=1,stress_end=6,drop_bps=3000);r=sim.create(c,99);r['location']='FINANCE'
 sim.financial(r,'POLICY_BUY',{'product_id':'CARDIF_VUL','amount_minor':1000000});p=r['policies'][0];start=p['account_minor']
 for _ in range(6):sim.monthly(r)
 assert all(price==7000 for price in r['prices'].values())
 assert p['account_minor']<start and p['fees_paid_minor']>30000
 assert all(s['drift_bps']<t['drift_bps'] for s in catalog.STOCKS[:5] for t in catalog.STOCKS[5:])
 assert len(catalog.STOCKS)==len(set(s['id'] for s in catalog.STOCKS))==20

def test_complete_course_with_actions_and_teacher_report(teacher):
 g=teacher;c=publish(g,save(g,reviewed=True));cl=classroom(g,c);r=join(g,cl);r=action(g,r,'MOVE',{'location':'FINANCE'})
 q=quote(g,r,'POLICY_BUY',{'product_id':'CARDIF_VUL','amount_minor':1000000});r=action(g,r,q['action'],q['params'],True);r=action(g,r,'MOVE',{'location':'HOME'})
 seen=0
 for _ in range(120):
  if r['state']['status']=='ENDED':break
  if r['state']['status']=='EVENT':
   answer=next(e['correct_id'] for e in c['events'] if e['id']==r['state']['event']['id']);r=action(g,r,'DECIDE',{'choice_id':answer});seen+=1
  elif r['state']['status']=='RESULT':r=action(g,r,'ACK')
  else:r=action(g,r,'ROLL')
 assert r['state']['status']=='ENDED' and r['state']['month']==36 and seen>=3
 assert r['state']['report']['score']==100
 assert call(g,'GET','/runs/'+r['id'])==r
 rep=call(g,'GET','/admin/classes/'+cl['id']+'/report');assert rep['completed']==1 and rep['learners'][0]['score']==100
 assert all(v['incorrect']==0 for v in rep['topics'].values())
 action(g,r,'ROLL',status=409)

def test_pending_jobs_recover_without_losing_originals(teacher):
 c=save(teacher);j=call(teacher,'POST','/admin/ai-jobs',{'course_id':c['id']})
 with store.tx() as db:
  job=jobs.job(db,db.execute('SELECT id FROM users').fetchone()[0],j['id']);job.update(status='RUNNING',_instance='previous-process');jobs.save(db,job)
 assert call(teacher,'GET','/admin/ai-jobs')[0]['status']=='INTERRUPTED'

def test_shared_sample_trial_and_instructor_isolation(teacher):
 g=teacher;c=save(g)
 assert call(g,'POST','/admin/courses/cardif-intro-20261027/trial',{})['state']['status']=='PLAYING'
 g.client=TestClient(app);g.csrf=None;g.auth('teacher3@example.test')
 with store.tx() as db:db.execute('INSERT INTO training_admins SELECT id FROM users WHERE email=?',('teacher3@example.test',))
 assert c['id'] not in {x['id'] for x in call(g,'GET','/courses')}
 call(g,'POST','/admin/courses/'+c['id']+'/trial',{},403)

def test_provider_contract_fake_transport_only(teacher,monkeypatch):
 from app import qwen
 c=save(teacher);monkeypatch.setenv('LIFE_TRAINING_LLM_ENABLED','1')
 monkeypatch.setattr(qwen,'config',lambda:{'enabled':True})
 valid={'contract_version':'training-author-v1','events':copy.deepcopy(c['events']),'extracted_facts':[{'source_id':'vul','text':'投保前确认费用'}],'unresolved':[]}
 monkeypatch.setattr(qwen,'generate',lambda *a,**k:json.dumps(valid,ensure_ascii=False))
 result=jobs.provider_generate(c,lambda:False)
 assert '確認費用' in result['extracted_facts'][0]['text']
 valid['events'][0].update(loss_minor=999,loss_kind='LIVING')
 with pytest.raises(ValueError,match='AI_OUTPUT_INVALID'):jobs.provider_generate(c,lambda:False)
 monkeypatch.setenv('LIFE_TRAINING_LLM_ENABLED','0')
 monkeypatch.setattr(qwen,'config',lambda:pytest.fail('disabled path read provider config'))
 with pytest.raises(ValueError,match='LLM_DISABLED'):jobs.provider_generate(c,lambda:False)

def test_default_curriculum_coverage_and_frozen_class_plan(teacher,monkeypatch):
 c=catalog_course()
 for seed in range(100):assert {x['template']['id'] for x in sim.plan(c,seed)}=={e['id'] for e in c['events']}
 cl=classroom(teacher);monkeypatch.setattr(sim,'plan',lambda *a:pytest.fail('joining must reuse frozen class plan'))
 assert join(teacher,cl)['state']['status']=='PLAYING'

def test_term_life_fixed_benefit_is_not_expense_reimbursement():
 r=sim.create(catalog_course(),8);r['location']='FINANCE';sim.financial(r,'POLICY_BUY',{'product_id':'CARDIF_CREDIT'});p=r['policies'][0]
 r['history']=[{'event_id':'disability','month':1,'loss_kind':'TERM_LIFE','loss_minor':5000000}];r['month']=1
 q=sim.quote(r,'CLAIM',{'event_id':'disability','policy_id':p['id']});assert q['result']['approved_minor']==p['face_minor'] and p['status']=='ACTIVE'
 sim.financial(r,'CLAIM',q['params']);assert p['status']=='CLAIM_PENDING'
 r['history'].append(dict(r['history'][0],event_id='second'))
 with pytest.raises(ValueError):sim.financial(r,'CLAIM',{'event_id':'second','policy_id':p['id']})
 sim.monthly(r);assert p['status']=='PAID_OUT' and r['claims'][0]['status']=='PAID'

def test_term_life_event_need_not_have_reimbursable_expenses():
 r=sim.create(catalog_course(),8);r['location']='FINANCE';sim.financial(r,'POLICY_BUY',{'product_id':'CARDIF_CREDIT'});p=r['policies'][0]
 r['history']=[{'event_id':'disability','month':1,'loss_kind':'TERM_LIFE','loss_minor':0}];r['month']=1
 assert sim.quote(r,'CLAIM',{'event_id':'disability','policy_id':p['id']})['result']['approved_minor']==p['face_minor']

def test_long_material_context_is_bounded_and_does_not_mutate_course(teacher):
 c=save(teacher);c['sources'].update({f'page-{i}':{'id':f'page-{i}','title':'保單教材','locator':str(i),'url':'','text':'費用給付除外風險'*225} for i in range(200)})
 original=copy.deepcopy(c);context,cut=jobs.provider_context(c)
 assert len(json.dumps(context,ensure_ascii=False))<=22000 and cut>0 and c==original
 assert len(context['sources'])<len(c['sources']) and 'vul' in context['sources']
