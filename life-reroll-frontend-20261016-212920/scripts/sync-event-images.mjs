import {mkdirSync,readdirSync,readFileSync,writeFileSync} from 'node:fs';
const cards=JSON.parse(readFileSync('content/events.json','utf8'));
const known=new Map(cards.map(card=>[card.id,card]));
mkdirSync('public/events',{recursive:true});
const manifest=JSON.parse(readFileSync('public/event-media.json','utf8'));
manifest.events??={};
const priority=['webp','avif','png','jpg','jpeg'];
const files=readdirSync('public/events').sort((a,b)=>{
 const extension=name=>priority.indexOf(name.split('.').at(-1).toLowerCase());
 return extension(a)-extension(b)||a.localeCompare(b);
});
const found=new Set();let matched=0;
for(const file of files){
 const match=file.match(/^([a-z]{2}\d{2})\.(webp|avif|png|jpe?g)$/i);
 if(!match)continue;
 const id=match[1].toUpperCase(),card=known.get(id);
 if(!card){console.warn(`Unknown event ID: ${file}`);continue;}
 if(found.has(id)){console.warn(`Multiple images for ${id}; keeping ${manifest.events[id].src}`);continue;}
 found.add(id);manifest.events[id]={src:'/events/'+file,alt:card.title+'的事件情境'};matched++;
}
if(matched)writeFileSync('public/event-media.json',JSON.stringify(manifest,null,2)+'\n');
const kind=card=>({LIFE:'FAMILY',TRAVEL:'EXPENSE'}[card.kind]??card.kind);
const rows=cards.map(card=>`| ${card.id} | ${card.title} | ${kind(card)} | \`public/events/${card.id}.webp\` |`).join('\n');
writeFileSync('docs/EVENT_IMAGE_INDEX.md',`# 事件圖片對照表\n\n共 ${cards.length} 張事件卡。按編號命名圖片後，執行 \`pnpm sync:event-images\` 自動建立對應。也支援 .png、.jpg、.jpeg、.avif；請每個編號只放一張圖片。\n\n| 事件編號 | 事件名稱 | 類型 | 建議放置位置 |\n| --- | --- | --- | --- |\n${rows}\n`);
console.log(`Mapped ${matched} event images. Full index: docs/EVENT_IMAGE_INDEX.md`);
if(!matched)console.log('Place prepared images such as FA06.webp in public/events, then run this command again.');
