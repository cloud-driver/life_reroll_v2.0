import {useEffect,useRef,useState} from 'react';
import type {GameModel} from './use-game';
import './account-settings.css';
type VerificationState={email:string;verified:boolean;delivery_status:'NONE'|'QUEUED'|'SENDING'|'SENT'|'FAILED'|'DEVELOPMENT';retry_after_seconds:number;expires_in_seconds:number;attempts_remaining:number;development:boolean};
export function EmailVerification({game}:{game:GameModel}){
 const user=game.session!.user!,[value,setValue]=useState<VerificationState|null>(null),[code,setCode]=useState(''),[error,setError]=useState(''),[revision,setRevision]=useState(0),[now,setNow]=useState(Date.now());
 const loadedAt=useRef(Date.now());
 useEffect(()=>{const abort=new AbortController();setError('');
  void(async()=>{try{while(!abort.signal.aborted){
   const v=await game.api.send<VerificationState>({method:'GET',path:'/api/v1/me/email-verification',key:''},abort.signal);
   if(abort.signal.aborted)return;loadedAt.current=Date.now();setNow(Date.now());setValue(v);
   if(v.verified){await game.refresh(abort.signal);return;}
   if(!['QUEUED','SENDING'].includes(v.delivery_status))return;
   await new Promise<void>((resolve,reject)=>{const timer=setTimeout(done,1200);function done(){abort.signal.removeEventListener('abort',stop);resolve();}function stop(){clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));}abort.signal.addEventListener('abort',stop,{once:true});});
  }}catch{if(!abort.signal.aborted)setError('暫時無法確認寄送狀態；收到信後仍可輸入驗證碼，或重新讀取狀態。');}})();return()=>abort.abort();
 },[game.api,user.id,revision]);
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
 const elapsed=Math.floor((now-loadedAt.current)/1000),retry=Math.max(0,(value?.retry_after_seconds??0)-elapsed),expires=Math.max(0,(value?.expires_in_seconds??0)-elapsed);
 const labels={NONE:'尚未寄送驗證信。',QUEUED:'驗證信已排入寄送，可以先閱讀服務說明。',SENDING:'正在寄送驗證信…',SENT:'驗證信已寄出，請查看收件匣或垃圾郵件。',FAILED:'這次未能寄出驗證信，請稍後重寄。',DEVELOPMENT:'開發測試模式：不會寄出真實郵件。'};
 async function verify(){const ok=await game.perform(async()=>{await game.write('A06',{}, {email:user.email,token:code});setCode('');game.api.devToken='';await game.refresh();},'信箱已驗證，可以開始人生');if(!ok)setRevision(v=>v+1);}
 async function resend(){const ok=await game.perform(async()=>{await game.write('A05',{}, {email:user.email});setCode('');},'已重新申請驗證信，請使用最新驗證碼');if(ok)setValue(null);setRevision(v=>v+1);}
 return <section className="verification-card" aria-label="信箱驗證"><h3>先驗證你的信箱</h3><p>驗證碼會寄到 <strong>{user.email}</strong>，完成驗證後即可開始完整人生。</p><p role="status" className={`verification-status ${value?.delivery_status==='FAILED'?'verification-error':''}`}>{value?labels[value.delivery_status]:'正在確認寄送狀態…'}</p>
  {value?.delivery_status==='SENT'&&<p className="verification-status">{expires>0?`最新驗證碼剩餘約 ${Math.ceil(expires/60)} 分鐘有效。`:'驗證碼已失效，請重寄新碼。'}{value.attempts_remaining===0&&' 嘗試次數已用完，請重寄新碼。'}</p>}
  <form onSubmit={e=>{e.preventDefault();void verify();}}><label>六位數驗證碼<input value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,'').slice(0,6))} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required placeholder="000000"/></label><div className="play-actions"><button type="submit" disabled={game.busy||!game.online||code.length!==6||value?.attempts_remaining===0}>完成信箱驗證</button><button type="button" className="secondary" disabled={game.busy||!game.online||!value||retry>0} onClick={()=>void resend()}>{retry>0?`${retry} 秒後可重寄`:'重寄驗證信'}</button></div></form>
  {error&&<p role="alert" className="verification-error">{error}</p>}{error&&<button className="secondary" onClick={()=>setRevision(v=>v+1)}>重新確認寄送狀態</button>}<p className="verification-status">驗證碼 10 分鐘內有效，最多嘗試 5 次；重寄後請使用最新一封信。</p>
 </section>;
}
