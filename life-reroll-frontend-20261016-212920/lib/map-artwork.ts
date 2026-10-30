// Route coordinates always remain in this original, unmodified world space.
export const CITY_MAP={width:1672,height:941};
// Generated panorama: 2120 x 742. Match its height to the original world.
export const CITY_PANORAMA={width:2120/742*941,height:941};
export const CITY_REGIONS=[
 {id:'home',label:'生活區（家）',x:840,y:350,accent:'#a18a63'},
 {id:'work',label:'工作區',x:1490,y:620,accent:'#638493'},
 {id:'finance',label:'金融區',x:245,y:110,accent:'#658675'},
 {id:'leisure',label:'休閒區',x:1410,y:390,accent:'#929269'},
];
export function cityMapCamera(width:number,height:number){
 const ratio=height>0?width/height:CITY_MAP.width/CITY_MAP.height;
 const viewWidth=Math.max(CITY_MAP.width,Math.min(CITY_PANORAMA.width,CITY_MAP.height*ratio));
 return {x:(CITY_MAP.width-viewWidth)/2,y:0,width:viewWidth,height:CITY_MAP.height};
}
