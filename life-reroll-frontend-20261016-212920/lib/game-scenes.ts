import type {Scene} from './game-types';
export function scenePath(scenes:Scene[],from:string,to:string):string[]{
 if(from===to)return [];
 const queue:[string,string[]][]=[[from,[]]],visited=new Set([from]);
 while(queue.length){const [node,path]=queue.shift()!;for(const next of scenes.find(s=>s.id===node)?.connections??[]){if(visited.has(next))continue;const result=[...path,next];if(next===to)return result;visited.add(next);queue.push([next,result]);}}
 throw Error('目前場景沒有可前往的道路。');
}
