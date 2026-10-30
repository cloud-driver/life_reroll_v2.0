export type CoachTopic='overview'|'event'|'finance'|'insurance'|'review';
export type DemoCoachSnapshot={age:number;year:number;rolls:number;cash:number;savings:number;stocks:number};
export type CoachJob={id:string;run_id:string;run_version:number;kind:'COACH'|'REVIEW';topic:CoachTopic;status:'QUEUED'|'RUNNING'|'COMPLETE'|'FALLBACK'|'CANCELLED';question:string;text:string;sources:{label:string;text:string;resource_id:string|null}[];context_label:string;progress:string;notice:string;model:string|null;created_at:string};
