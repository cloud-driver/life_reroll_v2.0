import type {Course,Lesson,Source} from './training';
export const MAX_EVENT_SOURCES=8;
export type DraftIssue={message:string;eventIndex?:number;ruleKey?:string};
export function sourceIssue(event:Lesson,index:number,sources:Record<string,Source>):DraftIssue|null{
 const context=`第 ${index+1} 則情境「${event.title||'未命名'}」`;
 const count=event.source_ids.length;
 const message=!count?`${context}至少要選擇 1 項教學依據。`:count>MAX_EVENT_SOURCES?`${context}已選 ${count} 項教學依據，最多 ${MAX_EVENT_SOURCES} 項。請取消部分引用後再儲存。`:event.source_ids.some(id=>!sources[id])?`${context}的部分引用不在目前教案內。請重新選用相關商品／教材，或取消已失效的引用。`:new Set(event.source_ids).size!==count?`${context}重複引用相同來源，請移除重複項目。`:'';
 return message?{message,eventIndex:index}:null;
}
export function validateTrainingDraft(course:Course,sources:Record<string,Source>):DraftIssue|null{
 for(const [value,label,max] of [[course.title,'教案名稱',100],[course.audience,'授課對象',100],[course.instructions,'希望怎麼教',4000]] as const){if(!value.trim()||Array.from(value.trim()).length>max)return {message:`${label}須為 1 至 ${max} 字。`};}
 if(course.product_ids.length<1||course.product_ids.length>8)return {message:'請選擇 1 至 8 項商品或保險概念。'};
 if(course.material_ids.length>10)return {message:'每份教案最多選用 10 份教材。'};
 const r=course.rules;
 for(const [key,label,lo,hi,scale] of [['horizon_months','課程月份',12,120,1],['salary_minor','每月收入（元）',1000000,20000000,100],['living_bps','生活支出占收入（%）',5000,8500,100],['reserve_months','初始預備金（月生活費）',1,4,1],['drop_bps','累計跌幅（%）',1000,6000,100],['stress_start','壓力起始月',1,100,1],['stress_end','壓力結束月',2,120,1],['emphasis_multiplier','抽樣權重',1,5,1]] as const){if(!Number.isInteger(r[key])||r[key]<lo||r[key]>hi)return {message:`${label}須介於 ${lo/scale} 至 ${hi/scale}，${scale===100?'最多小數點後 2 位':'請填寫整數'}。`,ruleKey:key};}
 if(r.stress_start>=r.stress_end||r.stress_end>r.horizon_months)return {message:'壓力起始月須早於結束月，且結束月不能超過課程月份。',ruleKey:'stress_start'};
 if(r.guaranteed_topic&&!course.events.some(e=>e.topic===r.emphasis_topic))return {message:'所保證的主題尚未包含在教案中，請加入相應情境，或取消保證出現。'};
 if(course.events.length<1||course.events.length>12)return {message:'每份教案須有 1 至 12 則情境。'};
 for(const [i,event] of course.events.entries()){
  for(const [value,label,max] of [[event.title,'名稱',70],[event.lesson,'短教學',300],[event.prompt,'劇情與提問',400],[event.explanation,'短回饋',500],...event.choices.map((c,n)=>[c.label,`第 ${n+1} 項選項文字`,140] as const)] as const){if(!value.trim()||Array.from(value.trim()).length>max)return {message:`第 ${i+1} 則情境的${label}須為 1 至 ${max} 字。`,eventIndex:i};}
  const issue=sourceIssue(event,i,sources);if(issue)return issue;
  if(!Number.isInteger(event.loss_minor)||event.loss_minor<0||event.loss_minor>50000000)return {message:`第 ${i+1} 則情境的必要支出須為 0 至 500,000 元。`,eventIndex:i};
  if(event.loss_minor>0&&event.loss_kind==='NONE')return {message:`第 ${i+1} 則情境有必要支出時須選擇對應支出類型。`,eventIndex:i};
 }
 return null;
}
