import type { DestinationId } from './map-data';
export type TravelEvent =
  | {type:'trip:start'; destination:DestinationId; direction:'outbound'|'return'}
  | {type:'trip:milestone'; destination:DestinationId; direction:'outbound'|'return'; index:number}
  | {type:'trip:arrive'; destination:DestinationId; direction:'outbound'|'return'};
type Listener = (event:TravelEvent)=>void;
const listeners = new Set<Listener>();
// Future gameplay subscribes to route milestones without changing animation code.
export const travelEvents = {
  subscribe(listener:Listener) { listeners.add(listener); return () => {listeners.delete(listener)}; },
  emit(event:TravelEvent) { listeners.forEach(listener=>listener(event)); },
};
