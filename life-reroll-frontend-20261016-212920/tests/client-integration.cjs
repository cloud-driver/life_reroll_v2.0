// Exercises the actual TypeScript client through the frontend's API proxy and an isolated FastAPI process.
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {spawn,spawnSync}=require('node:child_process');
const assert=require('node:assert/strict');
const net=require('node:net');
const ts=require('typescript');
const Module=require('node:module');
function load(file){const filename=path.resolve(__dirname,'..',file);const m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText,filename);return m.exports;}
const {GameClient,GameApiError,configuredApiBase}=load('lib/game-client.ts');
const {GameRecovery}=load('lib/game-recovery.ts');
const {scenePath}=load('lib/game-scenes.ts');
const {visibleGamePanel,panelContext}=load('lib/game-panels.ts');
const {canTourFinance}=load('lib/tutorial.ts');
const memory=()=>{const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};};
global.sessionStorage=memory();
let checks=0;
const check=(condition,message)=>{assert.ok(condition,message);checks++;};
async function availablePort(){const listener=net.createServer();await new Promise(resolve=>listener.listen(0,'127.0.0.1',resolve));const port=listener.address().port;await new Promise(resolve=>listener.close(resolve));return port;}
async function stop(child){if(child.exitCode!==null)return;await new Promise(resolve=>{child.once('exit',resolve);child.kill('SIGTERM');});}
(async()=>{
 global.window={LIFE_CONFIG:{apiBase:'https://api.example.com/api/v1'}};
 check(configuredApiBase()==='https://api.example.com','runtime config strips API prefix');
 global.window.LIFE_CONFIG.apiBase='javascript:alert(1)';assert.throws(()=>configuredApiBase());checks++;
 const bad=new GameClient();await assert.rejects(()=>bad.call('B01'),e=>e.code==='API_CONFIG_INVALID');checks++;
 delete global.window;
 const lost=new GameClient(async()=>{throw Error('lost');},'');
 await assert.rejects(()=>lost.call('D01',{run_id:'run'},{expected_version:1}),e=>e instanceof GameApiError&&e.code==='CONNECTION_UNCERTAIN');checks++;
 const mailUnavailable=new GameClient(async()=>new Response(JSON.stringify({data:null,error:{code:'MAIL_NOT_CONFIGURED',message:'寄信服務尚未設定完成'}}),{status:503,headers:{'Content-Type':'application/json'}}),'');
 await assert.rejects(()=>mailUnavailable.call('A01',{},{}),e=>e.code==='MAIL_NOT_CONFIGURED'&&e.status===503);checks++;
 const storage=memory(),recovery=new GameRecovery(storage,'https://one.example');
 const plan=lost.plan('D01',{run_id:'run'},{expected_version:1});recovery.begin('user','D01',plan);
 check(recovery.read('user').request.key===plan.key,'same retry key retained');
 check(new GameRecovery(storage,'https://two.example').read('user')===null,'recovery isolated between API servers');
 recovery.begin('user','A02',lost.plan('A02',{}, {password:'must-not-save'}));
 check(!Array.from({length:1},()=>storage.getItem('life-reroll:recovery:v1:https://one.example:user')).join('').includes('must-not-save'),'auth secrets excluded');
 const run={id:'r',status:'EVENT_PENDING',scene_id:'HOSPITAL',pending_event_id:'e',advance_id:'a'};
 check(!canTourFinance(run),'tutorial does not move away from a pending medical event');
 check(!canTourFinance({...run,status:'EXPLORING',scene_id:'HOME',daily_phase:'WORK_REQUIRED'}),'tutorial preserves required work');
 check(!canTourFinance({...run,status:'TURN_REVIEW',scene_id:'HOME',daily_phase:'HOME_READY'}),'tutorial preserves pending settlement');
 check(canTourFinance({...run,status:'INITIAL_ALLOCATION',scene_id:'HOME',daily_phase:'HOME_READY'}),'initial tutorial may visit finance');
 check(visibleGamePanel(run,{name:'review',context:'old'},'',false)==='event','event has priority');
 check(visibleGamePanel(run,{name:'event',context:panelContext(run)},'',true)==='','moving hides dialog');
 check(scenePath([{id:'HOME',connections:['STREET']},{id:'STREET',connections:['WORK']},{id:'WORK',connections:[]}],'HOME','WORK').join(',')==='STREET,WORK','work navigation includes authoritative street transition');
 const port=await availablePort(),proxyPort=await availablePort();
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'reroll-client-'));
 const root=path.resolve(__dirname,'../..');
 const candidates=[process.env.LIFE_TEST_PYTHON,path.join(root,'backend/.venv/bin/python'),path.join(root,'.venv/bin/python')].filter(Boolean);
 const python=candidates.find(p=>fs.existsSync(p))||'python3';
 const child=spawn(python,['-m','app.main','--port',String(port)],{cwd:path.join(root,'backend'),env:{...process.env,LIFE_REPLAY_DB:path.join(tmp,'isolated.sqlite3'),LIFE_DEVELOPMENT_MODE:'1',LIFE_SKIP_EMAIL_VERIFICATION:'1',LIFE_EMAIL_MODE:'development',LIFE_AI_BASE_URL:'',LIFE_AI_API_KEY:'',LIFE_COACH_ENABLED:'0'},stdio:['ignore','ignore','pipe']});
 const proxy=spawn(python,[path.resolve(__dirname,'../serve.py'),'--port',String(proxyPort),'--api-proxy',`http://127.0.0.1:${port}`],{stdio:['ignore','ignore','pipe']});
 let logs='';child.stderr.on('data',b=>{logs=(logs+b).slice(-4000);});
 proxy.stderr.on('data',b=>{logs=(logs+b).slice(-4000);});
 const base=`http://127.0.0.1:${proxyPort}`;
 try{
  let ready=false;
  for(let i=0;i<60;i++){try{const res=await fetch(base+'/api/v1/bootstrap');if(res.ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}
  assert.ok(ready,logs);
  const api=new GameClient(undefined,base);
  const boot=await api.call('B01');check(boot.email_verification_required===false,'backend bypass reported');
  await api.call('A01',{}, {email:'integration@example.com',password:'TestPassword123!',display_name:'整合測試',terms_version:boot.terms_version,privacy_version:boot.privacy_version});
  await api.call('A02',{}, {email:'integration@example.com',password:'TestPassword123!'});
  check(!!(await api.session()).user,'bearer login without browser cookies');
  check((await api.call('A14')).tutorial_completed===false,'new account needs tutorial');
  await api.call('A15',{}, {tutorial_completed:true});
  check((await api.call('A14')).tutorial_completed===true,'tutorial completion survives a fresh settings read');
  const resumed=new GameClient(undefined,base);check(!!(await resumed.session()).user,'refresh restores bearer session');
  const other=new GameClient(undefined,base+'-other');check(!sessionStorage.getItem('life-reroll:session:'+other.apiBase),'tokens isolated per API origin');
  const cors=await fetch(`http://127.0.0.1:${port}/api/v1/campaigns`,{method:'OPTIONS',headers:{Origin:'http://127.0.0.1:5173','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type,idempotency-key'}});
  check(cors.status===200&&cors.headers.get('access-control-allow-origin')==='http://127.0.0.1:5173','CORS supports split-server preflight');
  let c=(await resumed.call('C01',{}, {locale:'zh-TW'})).campaign;
  let r=await resumed.call('C06',{run_id:c.current_run_id});
  const radar=await resumed.send(resumed.insightPlan(`/api/v1/runs/${r.id}/radar`));
  check(radar.method==='MODEL'&&radar.run_version===r.version,'trained radar through actual frontend proxy');
  await assert.rejects(()=>resumed.send(resumed.insightPlan(`/api/v1/runs/${r.id}/branches`)),e=>e.code==='REBIRTH_NOT_AVAILABLE');checks++;
  const coachBefore=JSON.stringify(r);
  const coachPlan=resumed.coachPlan(`/api/v1/runs/${r.id}/coach`,'POST',{expected_version:r.version,topic:'finance',question:'可用資金與淨資產差在哪？'});
  const coach=await resumed.send(coachPlan);
  check(coach.status==='FALLBACK'&&coach.sources.length>0,'coach fallback through actual frontend proxy');
  check((await resumed.send(coachPlan)).id===coach.id,'coach request safely replays');
  check(JSON.stringify(await resumed.call('C06',{run_id:r.id}))===coachBefore,'coaching does not change the run');
  const demoPlan=resumed.coachPlan('/api/v1/coach/demo','POST',{topic:'finance',question:'展示模式資金？',snapshot:{age:28,year:2026,rolls:0,cash:18000000,savings:30000000,stocks:8000000}},true);
  const demoCoach=await resumed.send(demoPlan);
  check((await resumed.send(resumed.coachPlan(`/api/v1/coach/jobs/${demoCoach.id}`,'GET',undefined,true))).run_id==='demo','demo capability works while full-game user is logged in');
  await assert.rejects(()=>resumed.send(resumed.coachPlan(`/api/v1/coach/jobs/${demoCoach.id}`)),e=>e.status===404);checks++;
  async function write(id,body={},params={}){const result=await resumed.call(id,{run_id:r.id,...params},{...body,expected_version:r.version});r=result.run??await resumed.call('C06',{run_id:r.id});return result;}
  const scenes=await resumed.call('B02');
  async function walk(to){for(const next of scenePath(scenes,r.scene_id,to))await write('C08',{scene_id:next});}
  async function finance(action,params){const quote=await resumed.call('E08',{run_id:r.id},{expected_version:r.version,action,params});assert.ok(quote.eligible,JSON.stringify(quote));await write('E10',{quote_id:quote.id,confirmed:true});}
  await walk('FINANCE');await finance('STOCK_BUY',{stock_id:'STABLE',quantity:10});await finance('POLICY_BUY',{product_id:'MEDICAL',coverage_minor:30000000,premium_period_months:12,beneficiary_label:'家人'});await walk('HOME');
  check(r.balances.stocks_market_value_minor>0,'stock purchase integrated');
  // Deterministic test-only scenario: coverage has time to take effect, then
  // a medical event and a travel event occur in adjacent simulation months.
  const fixture=spawnSync(python,['-c',`from app import store
with store.tx() as db:
    user=db.execute("SELECT id FROM users WHERE email='integration@example.com'").fetchone()['id']
    c=store.list_campaigns(db,user)[0]
    r=c['runs'][0]
    r['planned']=[{'at_index':8,'card_id':'FA17','anchor':False},{'at_index':9,'card_id':'TR01','anchor':False}]+[x for x in r['planned'] if x['at_index']>9 and x['card_id'] not in ('FA17','TR01')]
    store.put_campaign(db,c)
`],{cwd:path.join(root,'backend'),env:{...process.env,LIFE_REPLAY_DB:path.join(tmp,'isolated.sqlite3')},encoding:'utf8'});
  assert.equal(fixture.status,0,fixture.stderr);

  const counts={rolls:0,events:0,work:0,claims:0,rounds:0};
  for(let round=1;round<=3;round++){
   for(let step=0;step<300&&r.status!=='ENDED';step++){
    switch(r.status){
     case 'INITIAL_ALLOCATION':await write('C07');break;
     case 'EXPLORING':
      if(r.daily_phase==='WORK_REQUIRED'){await walk('WORK');await write('C08',{scene_id:'WORK',complete_work:true});counts.work++;}
      await walk('HOME');
      const request=resumed.plan('D01',{run_id:r.id},{expected_version:r.version});
      const a=await resumed.send(request);assert.deepEqual(await resumed.send(request),a);counts.rolls++;
      r=await resumed.call('C06',{run_id:r.id});break;
     case 'EVENT_PENDING':{
      const event=await resumed.call('D05',{run_id:r.id,event_id:r.pending_event_id});
      check(!!event.visual_key,'event art mapped by stable content ID');
      await write('D06',{choice_id:event.choices[0].id,confirmed:true},{event_id:event.id});counts.events++;break;}
     case 'FUNDING':{
      const eventId=r.pending_event_id;
      const assessment=await resumed.call('F07',{run_id:r.id,event_id:eventId});
      const claims=(await resumed.call('F09',{run_id:r.id},undefined,{event_id:eventId})).items;
      const item=assessment.items.find(i=>i.eligible&&!claims.some(c=>c.policy_id===i.policy_id));
      if(item){await write('F08',{event_id:eventId,policy_id:item.policy_id,benefit_code:item.benefit_code,evidence_ids:item.evidence_ids});counts.claims++;break;}
      const f=await resumed.call('D08',{run_id:r.id,event_id:eventId});
      if(f.can_pay)await write('D09',{}, {event_id:eventId});
      else if(f.can_wait)await write('D10',{}, {event_id:eventId});
      else if(f.can_confirm_failure)await write('D11',{}, {event_id:eventId});
      else{
       const portfolio=await resumed.call('E01',{run_id:r.id});
       const stock=portfolio.holdings.find(h=>h.quantity>0);
       const term=portfolio.term_deposits.find(t=>t.status==='ACTIVE');
       const room=f.options.find(o=>o.kind==='LOAN_BORROW')?.available_minor??0;
       if(stock)await finance('STOCK_SELL',{stock_id:stock.stock_id,quantity:stock.quantity});
       else if(term)await finance('TERM_CLOSE',{term_deposit_id:term.id});
       else if(room)await finance('LOAN_BORROW',{product_id:'SIM_LOAN',amount_minor:Math.min(room,f.remaining_minor),term_months:60});
       else throw Error('funding stalled '+JSON.stringify(f));
      }break;}
     case 'EVENT_RESULT':await write('D07',{}, {event_id:r.pending_event_id});break;
     case 'TURN_REVIEW':{
      const advance=await resumed.call('D02',{run_id:r.id,advance_id:r.advance_id});
      check(!!advance.opening_snapshot&&!!advance.closing_snapshot&&!!advance.summary,'settlement snapshots present');
      await write('D03',{}, {advance_id:r.advance_id});break;}
     default:throw Error('unexpected '+r.status);
    }
   }
   assert.equal(r.status,'ENDED');counts.rounds++;
   const report=await resumed.call('G01',{run_id:r.id});check(report.ending_net_worth_minor===r.balances.net_worth_minor,'report reconciles with final balance');
   const review=await resumed.send(resumed.coachPlan(`/api/v1/runs/${r.id}/coach`,'POST',{expected_version:r.version,kind:'REVIEW',topic:'review'}));
   check(review.status==='FALLBACK'&&review.text.includes(round===3?'未來可嘗試':'下一輪可嘗試'),'each completed life has a grounded pre-rebirth review');
   c=await resumed.call('C04',{campaign_id:c.id});
   if(round<3){
    const before=JSON.stringify(r),plan=resumed.insightPlan(`/api/v1/runs/${r.id}/branches`,'POST',{expected_version:r.version,expected_campaign_version:c.version});
    let branch=await resumed.send(plan);check((await resumed.send(plan)).id===branch.id,'branch analysis safely replays through proxy');
    check((await resumed.send(resumed.insightPlan(`/api/v1/runs/${r.id}/branches`))).id===branch.id,'branch polling reconnects to same job');
    const deadline=Date.now()+20000;
    while(['QUEUED','RUNNING'].includes(branch.status)){assert.ok(Date.now()<deadline,'branch timeout');await new Promise(resolve=>setTimeout(resolve,50));branch=await resumed.send(resumed.insightPlan(`/api/v1/insights/jobs/${branch.id}`));}
    check(branch.status==='COMPLETE'&&branch.results.length===branch.total_points,'every rewind point simulated in background');
    check(JSON.stringify(await resumed.call('C06',{run_id:r.id}))===before,'branch preview preserves completed life');
   }else{await assert.rejects(()=>resumed.send(resumed.insightPlan(`/api/v1/runs/${r.id}/branches`)),e=>e.code==='REBIRTH_NOT_AVAILABLE');checks++;}
   if(round<3){const points=await resumed.call('G02',{campaign_id:c.id});const chosen=points.at(-1);const preview=await resumed.call('G03',{campaign_id:c.id,point_id:chosen.id});const job=await resumed.call('G04',{campaign_id:c.id},{expected_campaign_version:preview.campaign_version,point_id:chosen.id,confirmed:true});r=await resumed.call('C06',{run_id:job.campaign.current_run_id});check(r.scene_id==='HOME'&&!r.advance_id,'rebirth starts at usable preparation scene');}
  }
  check(counts.claims>=1,'real frontend client submitted a medical claim');
  const exported=await resumed.call('G06',{campaign_id:c.id},{format:'PDF'});
  const file=await resumed.call('G07',{export_id:exported.job.result_ref.id});
  const priorStorage=global.sessionStorage;global.sessionStorage=memory();const anonymous=new GameClient(undefined,base);global.sessionStorage=priorStorage;
  await assert.rejects(()=>anonymous.download(file.download_url),e=>e.status===401);checks++;
  const pdf=await resumed.download(file.download_url);check((await pdf.text()).startsWith('%PDF'),'authenticated cross-origin PDF download');
  await assert.rejects(()=>resumed.download('https://other.example/report.pdf'));checks++;
  await resumed.call('A04',{},{});check(!(await new GameClient(undefined,base).session()).user,'logout clears persisted token');
  console.log(JSON.stringify({checks,counts,status:'PASS',coverage:'real TypeScript client + frontend API proxy + HTTP FastAPI; browser UI not exercised'},null,2));
 }finally{await Promise.all([stop(proxy),stop(child)]);fs.rmSync(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
