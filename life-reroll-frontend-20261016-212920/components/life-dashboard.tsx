'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Wallet, Heart, TrendingUp, RefreshCw, ChevronDown } from 'lucide-react';
import { backendRequest, DEMO_RUN, money, parseRun, STATUS_LABELS, type DashboardRun } from '@/lib/dashboard';
type Session={user:{display_name:string}|null;csrf_token:string};
export function LifeDashboard() {
  const [mode,setMode]=useState<'demo'|'backend'>('demo');
  const [run,setRun]=useState<DashboardRun|null>(DEMO_RUN);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [user,setUser]=useState<string|null>(null),[csrf,setCsrf]=useState('');
  const [local,setLocal]=useState(false),[connect,setConnect]=useState(false);
  const [email,setEmail]=useState(''),[password,setPassword]=useState('');
  const sequence=useRef(0);
  useEffect(()=>{
    const isLocal=['localhost','127.0.0.1','[::1]'].includes(window.location.hostname);
    setLocal(isLocal);
    try{if(isLocal&&sessionStorage.getItem('life-dashboard-mode')==='backend')void refresh();}catch{/* storage may be disabled */}
    return ()=>{sequence.current++};
  },[]);
  async function refresh(login=false) {
    const request=++sequence.current;
    try{sessionStorage.setItem('life-dashboard-mode','backend');}catch{/* optional preference */}
    setMode('backend');setRun(null);setBusy(true);setError('');
    try {
      let session=await backendRequest<Session>('/auth/session');
      if(login)session=await backendRequest<Session>('/auth/login',{method:'POST',body:{email,password},csrf:session.csrf_token||csrf});
      if(request!==sequence.current)return;
      setCsrf(session.csrf_token);setUser(session.user?.display_name??null);
      if(!session.user){setConnect(true);return;}
      const campaign=await backendRequest<{current_run_id:string|null}|null>('/campaigns/active');
      if(campaign?.current_run_id){
        const next=parseRun(await backendRequest(`/runs/${encodeURIComponent(campaign.current_run_id)}`));
        if(request===sequence.current)setRun(next);
      }
      if(login)setPassword('');
    }catch(e){if(request===sequence.current)setError(e instanceof Error?e.message:'無法連線至後端');}
    finally{if(request===sequence.current)setBusy(false);}
  }
  function demo(){try{sessionStorage.setItem('life-dashboard-mode','demo');}catch{/* optional preference */}sequence.current++;setMode('demo');setRun(DEMO_RUN);setBusy(false);setError('');setConnect(false);setPassword('');}
  function submit(e:FormEvent){e.preventDefault();void refresh(true);}
  const b=run?.balances;
  return <section className="life-dashboard" aria-label="人生儀表板">
    <div className="dashboard-heading"><div><span className="eyebrow">YOUR LIFE</span><h2>{run?.character.name??'我的人生'}</h2></div>
      <div className="dashboard-source"><span className={`source-badge ${mode==='demo'?'demo':''}`}>{mode==='demo'?'示範資料':'後端資料'}</span>
        {local&&<button type="button" onClick={()=>{setConnect(!connect)}} aria-expanded={connect}>連接遊戲</button>}
        {mode==='backend'&&<button type="button" onClick={()=>void refresh()} disabled={busy} aria-label="重新讀取人生資料"><RefreshCw size={15}/></button>}
      </div>
    </div>
    {connect&&local&&<div className="backend-connect">
      <p>本地後端：127.0.0.1:8000。使用已有帳號讀取進行中的人生。</p>
      <form onSubmit={submit}><label>電子郵件<input type="email" autoComplete="username" required value={email} onChange={e=>setEmail(e.target.value)}/></label><label>密碼<input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)}/></label><button disabled={busy}>登入並讀取</button></form>
      <div className="connect-actions"><button type="button" disabled={busy} onClick={()=>void refresh()}>讀取目前登入帳號</button><button type="button" onClick={demo}>使用示範資料</button></div>
      <small>新帳號與新人生請先在後端測試頁建立。地圖移動與互動 A／B／C 仍為動畫演示。</small>
    </div>}
    {error&&<p className="dashboard-message" role="alert">{error}。請確認後端正在執行；目前沒有顯示實際資產。</p>}
    {busy&&<p className="dashboard-message" role="status">正在讀取人生資料…</p>}
    {!busy&&!error&&!run&&<p className="dashboard-message">{user?`${user}，目前沒有進行中的人生，請先在後端測試頁開始遊戲。`:'請登入以讀取人生資料。'}</p>}
    {run&&b&&<>
      <div className="life-meta"><span>{run.age} 歲</span><span>{run.character.occupation}</span><span>第 {run.run_index}／3 輪</span><time>{run.sim_date}</time><span className="life-status">{STATUS_LABELS[run.status]??run.status}</span></div>
      <div className="dashboard-metrics">
        <div className="life-metric"><Wallet size={19}/><span>可用資金<small>現金＋活存</small></span><strong>NT$ {money(b.immediate_liquidity_minor)}</strong></div>
        <div className="life-metric"><TrendingUp size={19}/><span>淨資產<small>總資產扣除負債</small></span><strong className={b.net_worth_minor<0?'negative':''}>NT$ {money(b.net_worth_minor)}</strong></div>
        <div className="life-metric quality-metric"><Heart size={19}/><span>生活品質<small>每段人生的感受</small></span><strong>{run.quality??'—'}<small>／100</small></strong><progress max="100" value={run.quality} aria-label="生活品質"/></div>
      </div>
      <details className="asset-details"><summary>資產與生活明細<ChevronDown size={14}/><span>{run.pending_event_id?'有待處理事件':'目前無待處理事件'}</span></summary>
        <dl>{[['現金',b.cash_minor],['活存',b.savings_minor],['定存本金',b.term_principal_minor],['股票市值',b.stocks_market_value_minor],['保單現金價值',b.policy_cash_value_minor],['應收款（未入帳）',b.receivables_minor],['負債',b.liabilities_minor],['每月薪資',run.character.monthly_salary_minor]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>NT$ {money(value as number)}</dd></div>)}</dl>
        <p>連續負資產 {b.negative_years} 年。應收款不計入可用資金。{run.character.employment_status==='UNEMPLOYED'?'目前待業。':''}</p>
      </details>
    </>}
    <p className="dashboard-disclaimer">{mode==='demo'?'數值為版面示範；移動不會改變資產。':'資料取自目前登入的遊戲；移動演示不會執行後端交易。'} 教學模擬。</p>
  </section>;
}
