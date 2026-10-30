"""Deterministic regressions for issues exposed by live Tailscale/Qwen checks."""
import copy,json,threading,time
import pytest
from app import training_jobs as jobs,qwen,store
from app.zh import traditional
from test_training import teacher,game,call,save,classroom,join,action,catalog_course
from app import training_engine as sim

def test_choice_order_is_stable_and_does_not_reveal_correct_position():
 c=catalog_course(horizon_months=12);original=copy.deepcopy(c);positions=set()
 for seed in range(12):
  a=sim.create(c,seed);b=sim.create(c,seed)
  while a['status']=='PLAYING':sim.advance(a)
  while b['status']=='PLAYING':sim.advance(b)
  assert a['pending']==b['pending']
  e=a['pending'];positions.add(next(i for i,x in enumerate(e['choices']) if x['id']==e['correct_id']))
  public=sim.public(a)['event'];assert 'correct_id' not in public
  sim.decision(a,e['correct_id']);assert a['history'][-1]['correct']
 assert len(positions)>1 and c==original

def test_completed_generation_cannot_overwrite_a_newer_edit(teacher,monkeypatch):
 c=save(teacher);fake_provider(monkeypatch,c)
 j=call(teacher,'POST','/admin/ai-jobs',{'course_id':c['id']});jobs.POOL.submit(lambda:None).result(5)
 edited=call(teacher,'PUT','/admin/courses/'+c['id'],{**c,'title':'講師已更新','expected_version':c['version']})
 call(teacher,'POST','/admin/ai-jobs/'+j['id']+'/apply',{},409)
 assert next(x for x in call(teacher,'GET','/courses') if x['id']==c['id'])==edited

def test_workspace_character_limits_fail_before_creating_chat(monkeypatch):
 monkeypatch.setattr(qwen,'request',lambda *a,**kw:pytest.fail('Oversize request must not reach provider'))
 for system,text,tokens in [('s','x'*12001,100),('s'*4001,'x',100),('s','x',4097)]:
  with pytest.raises(qwen.ProviderError):qwen.generate({'base_url':'http://invalid','timeout':5},system,text,lambda *a:None,lambda *a:None,lambda:False,max_tokens=tokens)

def test_maximum_course_stays_within_real_provider_limit():
 c=catalog_course();c['instructions']='教學要求'*1000
 c['products']=[{**c['products'][0],'facts':['條款重點'*40]*8} for _ in range(8)]
 c['events']=[{**copy.deepcopy(c['events'][0]),'id':str(i),'prompt':'情境'*200,'lesson':'重點'*150,'explanation':'理由'*250,'choices':[{'id':str(j),'label':'選項'*65} for j in range(4)]} for i in range(12)]
 original=copy.deepcopy(c);ctx,cut=jobs.provider_context(c)
 assert len(json.dumps(ctx,ensure_ascii=False))<=11000 and cut and c==original

def valid(c):return {'contract_version':'training-author-v1','events':c['events'],'extracted_facts':[],'unresolved':[]}
def fake_provider(monkeypatch,c):
 monkeypatch.setenv('LIFE_TRAINING_LLM_ENABLED','1');monkeypatch.setattr(qwen,'config',lambda:{'enabled':True})
 def generate(settings,system,text,on_chat,on_text,cancelled,**kw):
  assert len(text)<=12000 and kw['max_tokens']<=4096
  on_chat('owned123','http://provider');on_text('{"contract_version":');return json.dumps(valid(c),ensure_ascii=False)
 monkeypatch.setattr(qwen,'generate',generate)

def test_ai_completion_apply_and_terminal_statuses(teacher,monkeypatch):
 c=save(teacher);fake_provider(monkeypatch,c)
 j=call(teacher,'POST','/admin/ai-jobs',{'course_id':c['id']});jobs.POOL.submit(lambda:None).result(5)
 j=call(teacher,'GET','/admin/ai-jobs')[0]
 assert j['status']=='COMPLETE' and j['progress_chars']>0 and j['elapsed_seconds']>=0 and j['sources']['vul']['url']
 assert not any(k.startswith('_') for k in j)
 applied=call(teacher,'POST','/admin/ai-jobs/'+j['id']+'/apply',{})
 assert not applied['reviewed'] and applied['status']=='DRAFT'
 assert call(teacher,'GET','/admin/ai-jobs')[0]['status']=='APPLIED'
 assert call(teacher,'POST','/admin/ai-jobs/'+j['id']+'/cancel',{})['status']=='APPLIED'
 call(teacher,'POST','/admin/ai-jobs/'+j['id']+'/retry',{},409)
 call(teacher,'POST','/admin/courses/'+c['id']+'/publish',{'expected_version':applied['version']},422)

def test_live_style_stop_is_not_queued_behind_generation(teacher,monkeypatch):
 c=save(teacher);r=join(teacher,classroom(teacher));started=threading.Event();release=threading.Event();stops=[]
 monkeypatch.setenv('LIFE_TRAINING_LLM_ENABLED','1');monkeypatch.setattr(qwen,'config',lambda:{'enabled':True})
 monkeypatch.setattr(qwen,'stop',lambda *a:stops.append(a))
 def slow(settings,system,text,on_chat,on_text,cancelled,**kw):
  on_chat('owned789','http://provider');on_text('draft');started.set();release.wait(5)
  if cancelled():raise qwen.Cancelled()
  return json.dumps(valid(c))
 monkeypatch.setattr(qwen,'generate',slow)
 j=call(teacher,'POST','/admin/ai-jobs',{'course_id':c['id']});assert started.wait(2)
 try:
  begin=time.monotonic();assert action(teacher,r,'ROLL')['state']['month']>0;assert time.monotonic()-begin<1
  stopped=call(teacher,'POST','/admin/ai-jobs/'+j['id']+'/cancel',{})
  assert stopped['status']=='CANCELLED' and stops==[('http://provider','owned789')]
 finally:release.set();jobs.POOL.submit(lambda:None).result(5)
 assert call(teacher,'GET','/admin/ai-jobs')[0]['status']=='CANCELLED'

def test_invalid_model_never_overwrites_course(teacher,monkeypatch):
 c=save(teacher);fake_provider(monkeypatch,c);bad=valid(c);bad['extracted_facts']=[{'text':'fake','source_id':'unknown'}]
 monkeypatch.setattr(qwen,'generate',lambda *a,**kw:json.dumps(bad))
 j=call(teacher,'POST','/admin/ai-jobs',{'course_id':c['id']});jobs.POOL.submit(lambda:None).result(5)
 j=call(teacher,'GET','/admin/ai-jobs')[0];assert j['status']=='FAILED' and j['error_code']=='AI_OUTPUT_INVALID'
 assert next(x for x in call(teacher,'GET','/courses') if x['id']==c['id'])['version']==c['version']

def test_unreachable_endpoints_show_clear_error_without_changing_draft(teacher,monkeypatch):
 c=save(teacher);fake_provider(monkeypatch,c)
 def unavailable(*args,**kwargs):raise qwen.ConnectionUnavailable('PROVIDER_UNREACHABLE')
 monkeypatch.setattr(qwen,'generate',unavailable)
 j=call(teacher,'POST','/admin/ai-jobs',{'course_id':c['id']});jobs.POOL.submit(lambda:None).result(5)
 j=call(teacher,'GET','/admin/ai-jobs')[0]
 assert j['status']=='FAILED' and j['error_code']=='PROVIDER_UNREACHABLE'
 assert '無法連線至 LLM' in j['message'] and '備援' in j['message']
 assert next(x for x in call(teacher,'GET','/courses') if x['id']==c['id'])==c

def test_semantic_mismatch_requires_review_and_reply_is_short(teacher,monkeypatch):
 c=save(teacher);fake_provider(monkeypatch,c);value=valid(c);event=next(e for e in value['events'] if e['loss_minor']);event['prompt']='客戶急需醫療費，應如何處理？'
 monkeypatch.setattr(qwen,'generate',lambda *a,**kw:json.dumps(value))
 result=jobs.provider_generate(c,lambda:False);assert any('事故敘述' in x for x in result['unresolved'])
 value['events'][0]['lesson']='重點'*100
 with pytest.raises(ValueError,match='AI_OUTPUT_INVALID'):jobs.provider_generate(c,lambda:False)
 assert traditional('扣除项目与费用')=='扣除項目與費用'
