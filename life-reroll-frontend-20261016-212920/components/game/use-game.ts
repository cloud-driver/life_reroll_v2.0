'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import {GameClient,GameApiError,receiptRun,type RequestPlan} from '@/lib/game-client';
import {GameRecovery} from '@/lib/game-recovery';
import type {Bootstrap,Campaign,RunState,Session,Job} from '@/lib/game-types';
export function useGame(){
 const api=useRef(new GameClient()).current;
 const [session,setSession]=useState<Session|null>(null),[campaign,setCampaign]=useState<Campaign|null>(null),[run,setRun]=useState<RunState|null>(null);
 const [bootstrap,setBootstrap]=useState<Bootstrap|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[online,setOnline]=useState(false),[job,setJob]=useState<Job|null>(null),[retry,setRetry]=useState<RequestPlan|null>(null);
 const [snapshotRevision,setSnapshotRevision]=useState(0),[completedJob,setCompletedJob]=useState<Job|null>(null);
 const recovery=useRef<GameRecovery|null>(null),userRef=useRef<string|null>(null);
 const bootstrapRef=useRef<Bootstrap|null>(null),readSequence=useRef(0);
 const runRef=useRef<RunState|null>(null),locked=useRef(false),mounted=useRef(false),pending=useRef<RequestPlan|null>(null);
 const updateRun=useCallback((next:RunState|null)=>{runRef.current=next;setRun(next);},[]);
 const refresh=useCallback(async(signal?:AbortSignal)=>{
  const sequence=++readSequence.current;
  if(!bootstrapRef.current){const boot=await api.call<Bootstrap>('B01',{},undefined,{},signal);if(!mounted.current||signal?.aborted)return;bootstrapRef.current=boot;setBootstrap(boot);}
  const current=await api.current(signal);if(!mounted.current||signal?.aborted||sequence!==readSequence.current)return;
  userRef.current=current.session.user?.id??null;
  if(userRef.current){const saved=recovery.current?.read(userRef.current);if(saved?.request){pending.current=saved.request;setRetry(saved.request);}else{pending.current=null;setRetry(null);}if(saved?.jobId){try{const tracked=await api.call<Job>('C12',{job_id:saved.jobId},undefined, {},signal);if(signal?.aborted||sequence!==readSequence.current)return;setJob(tracked);if(tracked.status==='SUCCEEDED'){setCompletedJob(tracked);recovery.current?.clear(userRef.current);setJob(null);return refresh(signal);}}catch(e){throw e;}}}
  else{pending.current=null;setRetry(null);setJob(null);setCompletedJob(null);}
  setSession(current.session);setCampaign(current.campaign);updateRun(current.run);setOnline(true);setSnapshotRevision(n=>n+1);
 },[api,updateRun]);
 const write=useCallback(async<T,>(id:string,params:Record<string,string>={},body?:unknown,versioned=false):Promise<T>=>{
  const savedTask=userRef.current?recovery.current?.read(userRef.current)?.jobId:null;
  if(savedTask&&id!=='C13'&&id!=='A04')throw Error('上一個背景任務仍待確認，請先重讀進度。');
  if(pending.current)throw Error('上一筆操作結果尚未確認，請先使用安全重試。');
  const input=versioned?{...(body as object??{}),expected_version:runRef.current?.version}:body;
  const plan=api.plan(id,params,input),durable=/^[CDEFG]/.test(id);
  if(durable&&userRef.current&&!recovery.current)throw Error('瀏覽器儲存不可用，請允許本站使用本機儲存後再操作。');
  if(durable&&userRef.current)try{recovery.current?.begin(userRef.current,id,plan);}catch{throw Error('瀏覽器無法保存操作識別，請允許本網站儲存資料後再試。');}
  pending.current=plan;
  try{const result=await api.send<T>(plan);pending.current=null;setRetry(null);if(durable&&userRef.current)recovery.current?.acknowledge(userRef.current,(result as {job?:Job})?.job?.id);const next=receiptRun(result);if(next)updateRun(next);return result;}
  catch(e){if(e instanceof GameApiError&&e.code==='CONNECTION_UNCERTAIN')setRetry(plan);else{pending.current=null;if(durable&&userRef.current)recovery.current?.clear(userRef.current);}throw e;}
 },[api,updateRun]);
 const perform=useCallback(async(task:()=>Promise<unknown>,success?:string)=>{
  if(locked.current)return false;locked.current=true;setBusy(true);setError('');setNotice('');
  try{await task();if(mounted.current&&success)setNotice(success);return true;}
  catch(e){if(!mounted.current)return false;setError(e instanceof Error?e.message:'操作未完成');
   if(e instanceof GameApiError&&e.status===0)setOnline(false);
   if(e instanceof GameApiError&&[401,403,409].includes(e.status))try{await refresh();}catch{/* preserve original failure */}
   return false;
  }finally{locked.current=false;if(mounted.current)setBusy(false);}
 },[refresh]);
 useEffect(()=>{
  mounted.current=true;try{recovery.current=new GameRecovery(localStorage,api.apiBase);}catch{/* writes report unavailable storage */}
  const controller=new AbortController();
  void (async()=>{try{await refresh(controller.signal);}catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'後端尚未連線');}})();
  return()=>{mounted.current=false;controller.abort();};
 },[api,refresh]);
 useEffect(()=>{
  if(run?.status!=='ADVANCING'&&(!job||['SUCCEEDED','FAILED'].includes(job.status)))return;
  const timer=setTimeout(()=>void perform(()=>refresh()),2000);return()=>clearTimeout(timer);
 },[run,job,busy,perform,refresh]);
 const queued=useCallback(async(value:{job:Job})=>{
  const final=await api.waitJob(value.job,j=>setJob(j));
  if(final.status==='FAILED')throw new GameApiError(final.error_code??'JOB_FAILED',409,'背景任務未完成，可依提示重試。');
  setCompletedJob(final);if(userRef.current)recovery.current?.clear(userRef.current);setJob(null);await refresh();return final;
 },[api,refresh]);
 async function retryOriginal(){if(!retry)return;await perform(async()=>{let result:unknown;try{result=await api.send(retry);}catch(e){if(e instanceof GameApiError&&e.status>0){setRetry(null);pending.current=null;if(userRef.current)recovery.current?.clear(userRef.current);}throw e;}const next=receiptRun(result);if(next)updateRun(next);setRetry(null);pending.current=null;if(userRef.current)recovery.current?.acknowledge(userRef.current,(result as {job?:Job})?.job?.id);const queued=result as {job?:Job};if(queued?.job){const final=await api.waitJob(queued.job,setJob);if(final.status==='FAILED')throw new GameApiError(final.error_code??'JOB_FAILED',409,'背景任務未完成，可重試準備任務。');}if(userRef.current)recovery.current?.clear(userRef.current);setJob(null);await refresh();},'已確認原操作結果');}
 return {api,session,campaign,run,snapshotRevision,completedJob,bootstrap,busy,error,notice,online,job,retry,refresh,write,perform,queued,retryOriginal,setNotice};
}
export type GameModel=ReturnType<typeof useGame>;
export function useResource<T>(game:GameModel,id:string,params:Record<string,string>,enabled=true,query:Record<string,string>={}){
 const [resource,setResource]=useState<{key:string;value:T|null;error:string;loading:boolean}>({key:'',value:null,error:'',loading:false});
 const [revision,setRevision]=useState(0);
 // Scene definitions follow the content version; account settings do not
 // change when moving between scenes. Explicit sync still refreshes settings.
 const runScoped=id!=='B02'&&id!=='A14';
 const key=JSON.stringify([id,params,query,runScoped?game.run?.id:null,runScoped?game.run?.version:null,game.session?.user?.id,game.snapshotRevision,enabled,revision]);
 useEffect(()=>{
  if(!enabled){setResource({key,value:null,error:'',loading:false});return;}
  const abort=new AbortController();setResource({key,value:null,error:'',loading:true});
  void (async()=>{try{const value=await game.api.call<T>(id,params,undefined,query,abort.signal);if(!abort.signal.aborted)setResource({key,value,error:'',loading:false});}catch(e){if(!abort.signal.aborted)setResource({key,value:null,error:e instanceof Error?e.message:'資料無法讀取',loading:false});}})();
  return()=>abort.abort();
  // key captures the complete resource identity; api is a stable client.
  // eslint-disable-next-line react-hooks/exhaustive-deps
 },[key,game.api]);
 // Never expose a previous event/resource for one paint before the effect resets it.
 const current=resource.key===key?resource:{value:null,error:'',loading:enabled};
 return {...current,reload:()=>setRevision(n=>n+1)};
}
