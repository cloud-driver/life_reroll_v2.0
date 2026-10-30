'use client';
import {Brand} from '@/components/brand';
import './game.css';
import './workspace.css';
import './settlement.css';
import './finance.css';
import './event-presentation.css';
import './routine.css';
import './hospital.css';
import './viewport.css';
import './layout.css';
import {useEffect,useState,useRef} from 'react';
import {allowed} from '@/lib/game-client';
import {automaticPanel,panelContext,visibleGamePanel} from '@/lib/game-panels';
import {scenePath} from '@/lib/game-scenes';
import {money,STATUS_LABELS} from '@/lib/dashboard';
import {DESTINATIONS,HOME,type DestinationId,type Point} from '@/lib/map-data';
import {buildTrip,sampleAtTime} from '@/lib/travel';
import type {Scene,LifestyleOption,Advance,Settings} from '@/lib/game-types';
import {useGame,useResource} from './use-game';
import {GameMap,type MapTrip} from './game-map';
import {DiceInteraction} from './dice-interaction';
import {GameDialog} from './game-dialog';
import {TutorialCoach,useGuidedTour} from './tutorial';
import {canTourFinance,fullTutorialSteps} from '@/lib/tutorial';
import {RoutineScene,RoutineTravel} from './routine-scene';
import {AccountPanel} from './account-panel';
import {FinancePanel} from './finance-panel';
import {EventPanel} from './event-panel';
import {ReportPanel} from './report-panel';
import {CoachWidget} from './coach';
import {RiskRadar} from './insights';
import {ExtrasPanel,AdminPanel} from './extras-panel';
import {AssetsPanel,InsurancePanel,SettlementPanel} from './insight-panels';
const sceneIds:Record<DestinationId,string>={finance:'FINANCE',hospital:'HOSPITAL',work:'WORK',leisure:'LEISURE'};
const destination=(scene:string)=>Object.keys(sceneIds).find(k=>sceneIds[k as DestinationId]===scene) as DestinationId|undefined;
const menu=[['overview','◉','人生總覽'],['assets','▤','資產與收支'],['insurance','◇','保險與理賠'],['event','▧','事件與理賠'],['review','▦','階段結算'],['reports','↺','人生回顧'],['settings','⚙','設定與教學']];
export function GameApp(){
 const game=useGame(),r=game.run,c=game.campaign;
 const [panelRequest,setPanelRequest]=useState({name:'',context:''}),[dismissed,setDismissed]=useState('');
 const [expanded,setExpanded]=useState(false),[moving,setMoving]=useState(false),[trip,setTrip]=useState<MapTrip|null>(null),[parked,setParked]=useState<Point>(HOME),[heading,setHeading]=useState(-30),[rolling,setRolling]=useState(false),[roll,setRoll]=useState<number|null>(null),[lifestyle,setLifestyle]=useState('');
 const actionLock=useRef(false),alive=useRef(false),travelQueue=useRef<MapTrip[]>([]);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 const scenes=useResource<Scene[]>(game,'B02',{},!!game.session?.user,c?{content_version:c.content_version}:{});
 const lifestyles=useResource<LifestyleOption[]>(game,'E14',{run_id:r?.id??''},!!r);
 const preferences=useResource<Settings>(game,'A14',{},!!game.session?.user);
 const [endingTutorial,setEndingTutorial]=useState(false),[reducedMotion,setReducedMotion]=useState(false);
 useEffect(()=>{setReducedMotion(false);},[game.session?.user?.id]);
 useEffect(()=>{if(preferences.value)setReducedMotion(preferences.value.reduced_motion);},[preferences.value]);
 useEffect(()=>{document.documentElement.dataset.reducedMotion=String(reducedMotion);return()=>{delete document.documentElement.dataset.reducedMotion;};},[reducedMotion]);
 const tour=useGuidedTour({ready:!!r&&!!preferences.value&&!game.busy&&!moving&&!rolling&&!game.retry,
  completed:preferences.value?.tutorial_completed,storageKey:game.session?.user?`life-reroll:tutorial:full:v1:${game.api.apiBase}:${game.session.user.id}`:'',
  buildSteps:()=>fullTutorialSteps(canTourFinance(r))});
 useEffect(()=>{setPanel('');setTrip(null);setMoving(false);setRoll(null);setParked(HOME);actionLock.current=false;},[r?.id]);

 useEffect(()=>{if(!r||moving)return;const id=destination(r.scene_id);if(id){const last=sampleAtTime(buildTrip(id,'outbound'),1);setParked(last.position);setHeading(last.heading);}},[r?.id,r?.scene_id,moving]);
 useEffect(()=>{if(r)setLifestyle(r.lifestyle);},[r?.id,r?.lifestyle]);
 useEffect(()=>{if(preferences.value)document.documentElement.style.fontSize=`${16*preferences.value.text_scale}px`;return()=>{document.documentElement.style.fontSize='';};},[preferences.value]);
 async function rollDice(){
  if(r&&!r.daily_phase){game.setNotice('請先重新啟動 8000 後端並重新整理，載入新的上班流程。');return;}
  if(!r||actionLock.current||game.busy||game.retry||!allowed(r,'ROLL'))return;
  actionLock.current=true;setPanel('');setRoll(null);setRolling(true);
  try{await game.perform(async()=>{const a=await game.write<Advance>('D01',{run_id:r.id},{},true);if(!alive.current)return;setRoll(a.roll_value);await new Promise(resolve=>setTimeout(resolve,reducedMotion?100:850));if(alive.current)await game.refresh();});}finally{actionLock.current=false;if(alive.current)setRolling(false);}
 }
 async function move(target:string){
  if(!r||!scenes.value||actionLock.current||game.busy||game.retry||!allowed(r,'SCENE_TRANSITION'))return;
  const from=r.scene_id,id=destination(target==='HOME'?from:target);
  actionLock.current=true;setMoving(true);setPanel('');
  const ok=await game.perform(async()=>{
   for(const scene of scenePath(scenes.value!,from,target))await game.write('C08',{run_id:r.id},{scene_id:scene},true);
   await game.refresh();
   if(alive.current&&id){
    const source=destination(from);
    travelQueue.current=source&&target!=='HOME'&&source!==id?[{id,direction:'outbound',nonce:Date.now()+1}]:[];
    setTrip({id:travelQueue.current.length?source!:id,direction:target==='HOME'||travelQueue.current.length?'return':'outbound',nonce:Date.now()});
   }
  });
  if(!ok||!id){actionLock.current=false;setMoving(false);if(!ok)await game.perform(()=>game.refresh());}
 }
 function arrive(){if(!trip)return;const last=sampleAtTime(buildTrip(trip.id,trip.direction),1);setParked(last.position);setHeading(last.heading);const next=travelQueue.current.shift();if(next){setTrip(next);return;}setTrip(null);setMoving(false);actionLock.current=false;}
 useEffect(()=>{
  const target=tour.step?.scene;
  if(tour.active&&target&&r&&r.scene_id!==target&&canTourFinance(r)&&!game.busy&&!moving&&!rolling&&!endingTutorial&&!game.error&&!scenes.error)void move(target);
 },[tour.active,tour.step?.id,r?.scene_id,game.busy,moving,rolling,endingTutorial,game.error,scenes.value,scenes.error]);
 const normalPanel=visibleGamePanel(r,panelRequest,dismissed,rolling||moving);
 const panel=tour.active?(moving||rolling||(tour.step?.scene&&r?.scene_id!==tour.step.scene)?'':tour.step?.panel??''):normalPanel;
 function setPanel(name:string){setPanelRequest({name,context:panelContext(r)});if(name){const stage=automaticPanel(r);setDismissed(stage&&stage.name!==name?stage.key:'');}}
 function closePanel(){setDismissed(automaticPanel(r)?.key??'');setPanelRequest({name:'',context:panelContext(r)});}
 const busy=game.busy||moving||rolling||!!game.retry;
 const interactionGame={...game,busy};
 const canMove=game.online&&!busy&&allowed(r,'SCENE_TRANSITION')&&!!scenes.value;
 const at=r?destination(r.scene_id):undefined;

 async function finishTutorial(){
  if(game.busy||moving||rolling||endingTutorial)return;
  setEndingTutorial(true);tour.remember();
  try{
   await game.perform(async()=>{await game.write('A15',{}, {tutorial_completed:true});await game.refresh();});
   if(r?.scene_id==='FINANCE'&&canTourFinance(r))await move('HOME');
  }finally{tour.stop();setPanel('');setDismissed('');setEndingTutorial(false);}
 }
 const tutorialWaiting=!!(tour.step?.scene&&r&&r.scene_id!==tour.step.scene&&!game.error&&!scenes.error);
 const tutorialGuide=tour.active&&tour.step?<TutorialCoach key={tour.step.id} step={tour.step} index={tour.index} total={tour.total}
  busy={busy||endingTutorial||tutorialWaiting} onBack={()=>tour.go(-1)} onNext={()=>tour.index===tour.total-1?void finishTutorial():tour.go(1)} onExit={()=>void finishTutorial()}/>:undefined;
 const needsAccount=!game.session?.user||(!r)||((game.bootstrap?.email_verification_required??true)&&!game.session.user.email_verified);
 const title=panel==='event'&&r?.scene_id==='HOSPITAL'?'醫院 · 事件處理':menu.find(([id])=>id===panel)?.[2]??({hospital:'醫院服務',finance:'金融大樓',account:'帳號',admin:'內容管理'} as Record<string,string>)[panel]??'查看資料';
 return <main className={`play-shell game-workspace ${expanded?'nav-expanded':''}`}>
 {rolling&&<DiceInteraction value={roll}/>}
 <header className="workspace-header"><strong><Brand/></strong><span className="workspace-status">{r?`${r.age} 歲 · ${r.sim_date} · 第 ${r.run_index} 輪`:'人生讀檔 · 整合版'}</span><span>{game.online?'已連線':'未連線'}</span>{r&&<span className="workspace-autosave" role="status">{game.retry?'結果待確認':game.busy?'處理中…':'已自動儲存'}</span>}<button className="secondary" disabled={busy} onClick={()=>void game.perform(()=>game.refresh(),'進度已同步')}>同步</button><a href="/training" className="workspace-training-link">通路訓練</a><a href="/demo">免登入展示</a></header>
 <div className="workspace-body"><nav className="workspace-nav" aria-label="查閱儀表板"><button aria-label="展開或收合查閱選單" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>☰</button>{menu.map(([id,icon,label])=><button key={id} title={label} aria-label={label} disabled={rolling||(!r&&id!=='settings')} onClick={()=>setPanel(id)}><span aria-hidden="true">{icon}</span><span className="nav-label">{label}</span></button>)}<button title="帳號" aria-label="帳號" disabled={busy} onClick={()=>setPanel('account')}><span>♙</span><span className="nav-label">帳號</span></button>{game.session?.user?.roles.includes('CONTENT_ADMIN')&&<button disabled={busy} onClick={()=>setPanel('admin')}>管理</button>}</nav>
 <section className="workspace-stage" aria-label="城市與場域"><div className="workspace-hud">{r?<><div><span>可用資金</span><strong>{money(r.balances.immediate_liquidity_minor)} 元</strong></div><div><span>淨資產</span><strong>{money(r.balances.net_worth_minor)} 元</strong></div><div><span>人生狀態</span><strong>{STATUS_LABELS[r.status]}</strong></div></>:<p>{game.session?.user?game.session.user.email_verified?'準備好了，就開始你的新人生。':'先完成信箱驗證，即可開始新人生。':'登入後恢復進度，或由右上角進入免登入展示。'}</p>}</div>
 <div className="workspace-map-viewport">{needsAccount?<div className="workspace-welcome"><AccountPanel game={interactionGame}/>{!game.online&&game.error&&<p>請先啟動 8000 後端。</p>}</div>:r&&!moving&&(at||r.scene_id==='HOME')?<RoutineScene game={interactionGame} at={at} onMove={target=>void move(target)} onRoll={()=>void rollDice()} onPanel={setPanel}/>:<GameMap trip={trip} parked={parked} parkedHeading={heading} reducedMotion={tour.active||reducedMotion} onArrive={arrive}/>}</div></section>
 <aside className="workspace-controls">{!needsAccount&&r.scene_id!=='HOME'&&<RoutineTravel game={interactionGame} canMove={canMove} onMove={target=>void move(target)} error={scenes.error}/>}</aside></div>
 {game.notice&&!tour.active&&!panel&&<div className="workspace-notice" role="status"><span>{game.notice}</span><button className="quiet" aria-label="關閉提示" onClick={()=>game.setNotice('')}>×</button></div>}
 {(game.error||game.retry||game.job?.status==='FAILED')&&<div className={`workspace-alert ${game.error?'error':''}`} role={game.error?'alert':'status'}><span>{game.error||(game.retry?'上一筆操作尚待確認':'任務未完成，可重試。')}</span>{game.retry&&<button disabled={game.busy} onClick={()=>void game.retryOriginal()}>確認原操作／安全重試</button>}{game.job?.status==='FAILED'&&game.job.retryable&&<button disabled={game.busy} onClick={()=>void game.perform(async()=>{const q=await game.write<import('@/lib/game-types').AsyncReceipt>('C13',{job_id:game.job!.id},{});await game.queued(q);})}>重試原任務</button>}</div>}
 {tour.active&&!panel&&<GameDialog title="遊玩教學" coachOnly guide={tutorialGuide} onClose={()=>void finishTutorial()}/>}
 {panel&&!rolling&&<GameDialog key={panel} title={title} drawer={!['review','event','reports','finance','hospital'].includes(panel)} wide={['review','event','reports','finance','hospital'].includes(panel)} guide={tutorialGuide} onClose={tour.active?()=>void finishTutorial():closePanel}><div className="dialog-content">{game.notice&&!tour.active&&<div className="dialog-notice" role="status"><span>{game.notice}</span><button className="quiet" aria-label="關閉提示" onClick={()=>game.setNotice('')}>×</button></div>}{game.error&&<p role="alert" className="play-banner error">{game.error}</p>}{game.retry&&<button disabled={game.busy} onClick={()=>void game.retryOriginal()}>確認原操作／安全重試</button>}
 {panel==='account'&&<AccountPanel game={interactionGame}/>}{panel==='settings'&&<ExtrasPanel game={interactionGame} onTutorial={r?tour.start:undefined} onMotionChange={setReducedMotion}/>}{panel==='admin'&&game.session?.user?.roles.includes('CONTENT_ADMIN')&&<AdminPanel game={interactionGame}/>}
 {r&&!tour.active&&['overview','assets','insurance','event','hospital','review','finance'].includes(panel)&&<CoachWidget key={panel} api={game.api} runId={r.id} version={r.version} topic={panel==='assets'?'finance':panel==='hospital'?'event':panel as 'overview'|'event'|'finance'|'insurance'|'review'}/>}
 {r&&!tour.active&&r.status!=='ENDED'&&panel==='overview'&&<RiskRadar api={game.api} runId={r.id} version={r.version} onAssets={()=>setPanel('assets')} onEvents={()=>setPanel('event')}/>}
 {r&&<>{panel==='overview'&&<section className="overview-panel"><h2>{r.character.name.endsWith('的人生')?r.character.name:`${r.character.name}的人生`}</h2><p>{r.character.occupation} · {r.age} 歲 · {r.sim_date}</p><p>生活品質 {r.quality}／100 · 第 {r.run_index}／3 輪</p><p>目前：{STATUS_LABELS[r.status]}</p><label>生活方案<select disabled={busy||!allowed(r,'CHANGE_LIFESTYLE')||r.scene_id!=='HOME'} value={lifestyle} onChange={e=>setLifestyle(e.target.value)}>{lifestyles.value?.map(x=><option key={x.code} value={x.code}>{x.label} · 每月 {money(x.monthly_living_minor)} 元</option>)}</select></label><button disabled={busy||!allowed(r,'CHANGE_LIFESTYLE')||r.scene_id!=='HOME'||lifestyle===r.lifestyle||!lifestyle} onClick={()=>void game.perform(async()=>{await game.write('C09',{run_id:r.id},{lifestyle},true);await game.refresh();},'生活方案已更新')}>套用生活方案</button><p>成功操作會自動保存。離線不會推進人生。</p></section>}{panel==='assets'&&<AssetsPanel game={interactionGame}/ >}{panel==='insurance'&&<InsurancePanel game={interactionGame}/ >}{(panel==='event'||panel==='hospital')&&<EventPanel game={interactionGame} onRewind={()=>setPanel('reports')}/ >}{panel==='review'&&<SettlementPanel game={interactionGame} onDone={()=>setPanel('')} onEvent={()=>setPanel('event')}/ >}{panel==='finance'&&<FinancePanel game={interactionGame}/ >}{panel==='reports'&&c&&<ReportPanel game={interactionGame} coaching={!tour.active}/>}</>}</div></GameDialog>}
 </main>;
}
