import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import './teacher-tutorial.css';

type Step={tab:string;target:string;title:string;text:string;example?:boolean};
const steps:Step[]=[
 {tab:'materials',target:'tabs',title:'一起準備你的第一堂課',text:'我會帶你走過教材、教案、AI 編課與開班流程。每一步都會切到實際頁面；先看一圈，再動手準備。'},
 {tab:'materials',target:'upload',title:'第一步，帶入你的教材',text:'在這裡選擇 PDF、DOCX、PPTX 或文字檔，再按「上傳並解析」。每檔最多 8 MB／100 頁；請使用已授權的教材。'},
 {tab:'materials',target:'materials',title:'先核對擷取的內容',text:'教材顯示「可編課」後，展開「核對擷取內容」比對原文。掃描圖片目前需要另做文字辨識，不能直接用來編課。'},
 {tab:'courses',target:'new-course',title:'從範本開始，比較容易',text:'按這裡建立新草稿，也可以選既有教案、複製為新草稿。接下來我會用暫時的範本帶你認識編輯區。'},
 {tab:'courses',target:'brief',title:'告訴我們，這堂課要教什麼',text:'填寫名稱、授課對象與「希望怎麼教」，例如讓新進理專理解保障與流動性的取捨。往下勾選要使用的商品與已解析教材。',example:true},
 {tab:'courses',target:'rules',title:'讓教學融入人生情境',text:'已替你展開設定。這裡能調整課程月份、生活費、加強主題及市場壓力；這些是遊戲假設與課程安排。',example:true},
 {tab:'courses',target:'event',title:'每個選擇，都要有教學目的',text:'已展開第一則情境。核對短教學、提問、選項、正確答案、回饋與來源；玩家選完，才會看到解說。',example:true},
 {tab:'courses',target:'workflow',title:'儲存草稿，接著往下走',text:'每頁底部都有步驟按鈕。這裡按「儲存草稿並前往 AI 編課」，會先儲存成功再帶你進入下一步；也可回到教材頁補充來源。',example:true},
 {tab:'ai',target:'ai',title:'AI 編課會在背景進行',text:'實際操作時先選好並儲存草稿，再按背景產生。可以離開、回來看進度或取消；完成後核對所有選項、答案與引用，再套用。'},
 {tab:'ai',target:'review',title:'核對完成，就能直接開班',text:'套用 AI 結果後可在同頁核對教案、答案與引用，處理待核對事項並勾選審核。底部「核對後發布，前往開班」會儲存審核、發布版本，再帶你建立班次。',example:true},
 {tab:'classes',target:'class-create',title:'把課程交給學員',text:'選擇已發布教案、填寫班次名稱，再建立八碼加入代碼。學員在「學員入口」登入並輸入代碼，就能加入同一班課程。'},
 {tab:'classes',target:'class-list',title:'最後，一起回顧學習成果',text:'在班次列表按「查看學習成效」，追蹤進度、判斷分數與待釐清主題。完成導覽後會回到原頁；上方「工作室教學」可隨時重看。'},
];
const remembered=new Set<string>();

export function useTeacherTutorial(ready:boolean,userId:string){
 const [index,setIndex]=useState<number|null>(null);
 const origin=useRef<{scroll:number;focus:HTMLElement|null;details:boolean[]}|undefined>(undefined);
 const key=`life-reroll:teacher-tutorial:v2:${userId}`;
 function start(){
  if(!ready)return;
  origin.current={scroll:window.scrollY,focus:document.activeElement as HTMLElement|null,
   details:Array.from(document.querySelectorAll<HTMLDetailsElement>('.tr-studio details'),e=>e.open)};
  setIndex(0);
 }
 useEffect(()=>{
  if(!ready||!userId||remembered.has(key))return;
  try{if(localStorage.getItem(key)==='done')return;}catch{/* A session-only tour still works when storage is blocked. */}
  remembered.add(key);start();
 },[ready,key,userId]);
 function finish(){
  remembered.add(key);try{localStorage.setItem(key,'done');}catch{/* Keep the preference for this loaded session. */}
  setIndex(null);
  requestAnimationFrame(()=>{
   const saved=origin.current;
   if(!saved)return;
   document.querySelectorAll<HTMLDetailsElement>('.tr-studio details').forEach((el,i)=>{el.open=saved.details[i]??false;});
   const focus=saved.focus?.isConnected&&saved.focus!==document.body?saved.focus:document.querySelector<HTMLButtonElement>('[data-teach-launch]');
   focus?.focus({preventScroll:true});window.scrollTo({top:saved.scroll,behavior:'instant'});
  });
 }
 return {active:index!==null,index:index??0,step:index===null?undefined:steps[index],total:steps.length,start,finish,
  back:()=>setIndex(i=>i===null?null:Math.max(0,i-1)),next:()=>setIndex(i=>i===null?null:Math.min(steps.length-1,i+1))};
}

export function TeacherTutorial({tour}:{tour:ReturnType<typeof useTeacherTutorial>}){
 const dialog=useRef<HTMLDialogElement>(null),card=useRef<HTMLElement>(null),next=useRef<HTMLButtonElement>(null);
 const [rect,setRect]=useState<{left:number;top:number;width:number;height:number}|null>(null);
 const step=tour.step!;
 useLayoutEffect(()=>{
  const el=dialog.current!,overflow=document.documentElement.style.overflow;
  el.showModal();document.documentElement.style.overflow='hidden';
  return()=>{el.close();document.documentElement.style.overflow=overflow;};
 },[]);
 useLayoutEffect(()=>{
  const target=document.querySelector<HTMLElement>(`[data-teach-target="${step.target}"]`);
  const opened:HTMLDetailsElement[]=[];
  for(let el:HTMLElement|null=target;el;el=el.parentElement){
   if(el instanceof HTMLDetailsElement&&!el.open){el.open=true;opened.push(el);}
  }
  let frame=0;
  function position(scroll=false){
   if(!target||!card.current)return;
   const studio=document.querySelector<HTMLElement>('.tr-studio')!;
   // Reserve room below the real page so even its last control can be shown above the conversation.
   studio.style.paddingBottom=`${card.current.offsetHeight+60}px`;
   if(scroll){next.current?.focus({preventScroll:true});window.scrollTo({top:Math.max(0,target.getBoundingClientRect().top+window.scrollY-28),behavior:'instant'});}
   const r=target.getBoundingClientRect(),bottom=card.current.getBoundingClientRect().top-18;
   const left=Math.max(8,r.left-6),top=Math.max(8,r.top-6);
   setRect({left,top,width:Math.max(0,Math.min(window.innerWidth-8,r.right+6)-left),height:Math.max(0,Math.min(bottom,r.bottom+6)-top)});
  }
  const observer=new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>position(true));});
  if(card.current)observer.observe(card.current);
  if(target)observer.observe(target);
  const resize=()=>position(true),scroll=()=>position();
  window.addEventListener('resize',resize);window.addEventListener('scroll',scroll,{passive:true});
  window.visualViewport?.addEventListener('resize',resize);
  position(true);
  return()=>{observer.disconnect();cancelAnimationFrame(frame);window.removeEventListener('resize',resize);window.removeEventListener('scroll',scroll);window.visualViewport?.removeEventListener('resize',resize);opened.forEach(el=>{el.open=false;});};
 },[step]);
 useEffect(()=>()=>{const studio=document.querySelector<HTMLElement>('.tr-studio');if(studio)studio.style.paddingBottom='';},[]);
 return createPortal(<dialog ref={dialog} className="tr-tour" aria-modal="true" aria-labelledby="tr-tour-title" aria-describedby="tr-tour-copy" onCancel={e=>{e.preventDefault();tour.finish();}}
  onKeyDown={e=>{
   if(e.key!=='Tab')return;
   const buttons=Array.from(dialog.current!.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
   const first=buttons[0],last=buttons[buttons.length-1],focused=document.activeElement;
   if(e.shiftKey&&(focused===first||!buttons.includes(focused as HTMLButtonElement))){e.preventDefault();last?.focus();}
   else if(!e.shiftKey&&(focused===last||!buttons.includes(focused as HTMLButtonElement))){e.preventDefault();first?.focus();}
  }}>
  {rect&&rect.height>0&&<div className="tr-tour-spotlight" aria-hidden="true" style={rect}/>}
  <section ref={card} className="tr-tour-card">
   <div className="tr-tour-top"><span>工作室教學 · {tour.index+1} / {tour.total}</span><button onClick={tour.finish}>略過教學</button></div>
   <div className="tr-tour-progress" aria-hidden="true"><span style={{width:`${(tour.index+1)/tour.total*100}%`}}/></div>
   <div key={tour.index} className="tr-tour-copy" aria-live="polite" aria-atomic="true"><h2 id="tr-tour-title">{step.title}</h2><p id="tr-tour-copy">{step.text}</p></div>
   <p className="tr-tour-note">{step.example?'畫面為暫時範本，不會儲存，也不會覆蓋你的編輯。':'導覽只切換畫面，不會上傳、生成或發布。'}</p>
   <div className="tr-tour-actions"><button disabled={tour.index===0} onClick={tour.back}>上一步</button><button ref={next} className="tr-primary" onClick={tour.index===tour.total-1?tour.finish:tour.next}>{tour.index===tour.total-1?'完成，開始編課':'下一步'}</button></div>
  </section>
 </dialog>,document.body);
}
