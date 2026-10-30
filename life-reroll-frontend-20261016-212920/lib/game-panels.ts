import type {RunState} from './game-types';
export type PanelRun=Pick<RunState,'id'|'status'|'scene_id'|'pending_event_id'|'advance_id'>;
export function panelContext(run:PanelRun|null){
 return run?JSON.stringify([run.id,run.status,run.scene_id,run.pending_event_id,run.advance_id]):'account';
}
export function automaticPanel(run:PanelRun|null):{name:string;key:string}|null{
 if(!run)return null;
 if(['EVENT_PENDING','FUNDING','EVENT_RESULT'].includes(run.status)&&run.pending_event_id)return {name:'event',key:`${run.id}:event:${run.pending_event_id}`};
 if(run.status==='TURN_REVIEW'&&run.advance_id)return {name:'review',key:`${run.id}:review:${run.advance_id}`};
 if(run.status==='ENDED')return {name:'reports',key:`${run.id}:reports`};
 return null;
}
export function visibleGamePanel(run:PanelRun|null,request:{name:string;context:string},dismissed:string,transitioning:boolean){
 if(transitioning||run?.status==='ADVANCING')return '';
 const stage=automaticPanel(run);
 if(stage&&stage.key!==dismissed)return stage.name;
 return request.context===panelContext(run)?request.name:'';
}
