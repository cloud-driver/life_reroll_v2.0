import type {Event} from './game-types';
export type EventMediaAsset={src:string;alt:string};
export type EventMediaManifest={events?:Record<string,EventMediaAsset>;kinds?:Partial<Record<Event['kind'],EventMediaAsset>>};
export function resolveEventMedia(manifest:EventMediaManifest,event:Event):EventMediaAsset|null{
 if(!manifest||typeof manifest!=='object')return null;
 const asset=(event.visual_key?manifest.events?.[event.visual_key]:undefined)??(event.hospital_visit?manifest.kinds?.HEALTH:undefined)??manifest.kinds?.[event.kind];
 if(!asset||typeof asset.src!=='string'||typeof asset.alt!=='string')return null;
 // Teammates ship local assets; external images do not receive player context.
 return asset.src.startsWith('/')&&!asset.src.startsWith('//')?asset:null;
}
export const EVENT_MEDIA_READY='life-reroll:event-media';
