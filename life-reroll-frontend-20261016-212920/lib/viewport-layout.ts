// Show the original map in narrow windows, revealing more outer scenery in banners.
export function fitMapViewport(width:number,height:number,inset=20){
 const availableWidth=Math.max(0,width-inset),availableHeight=Math.max(0,height-inset);
 const ratio=Math.max(1672/941,Math.min(2120/742,availableHeight?availableWidth/availableHeight:1672/941));
 const contentWidth=Math.min(availableWidth,availableHeight*ratio);
 return {width:Math.min(width,contentWidth+inset),height:Math.min(height,contentWidth/ratio+inset)};
}
